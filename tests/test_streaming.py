import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from ai.ollama import (
    OllamaClient,
    compact_history,
    model_options,
    placement_text,
    read_stream,
    streaming_enabled,
)
from core.stream_output import StreamPresenter


def lines(*chunks):
    response = MagicMock()
    response.iter_lines.return_value = [json.dumps(c).encode() for c in chunks]
    return response


class ReadStream(unittest.TestCase):
    def test_pieces_are_joined_and_timing_comes_from_the_last_chunk(self):
        seen = []
        data = read_stream(lines(
            {"message": {"content": "Hello "}},
            {"message": {"content": "there."}},
            {"message": {"content": ""}, "done": True,
             "prompt_eval_count": 50, "eval_count": 3},
        ), seen.append)
        self.assertEqual(seen, ["Hello ", "there."])
        self.assertEqual(data["message"]["content"], "Hello there.")
        self.assertEqual(data["prompt_eval_count"], 50)

    def test_a_broken_stream_keeps_the_text_so_far(self):
        response = MagicMock()
        def broken():
            yield json.dumps({"message": {"content": "Half an"}}).encode()
            yield b"{not json"
        response.iter_lines.return_value = broken()
        data = read_stream(response, lambda piece: None)
        self.assertEqual(data["message"]["content"], "Half an")

    def test_a_stream_that_fails_before_any_text_raises(self):
        response = lines({"error": "model not found"})
        with self.assertRaises(ValueError):
            read_stream(response, lambda piece: None)

    def test_a_failing_display_callback_does_not_lose_the_reply(self):
        def boom(piece):
            raise RuntimeError("screen")
        data = read_stream(lines(
            {"message": {"content": "Still here."}},
            {"done": True}), boom)
        self.assertEqual(data["message"]["content"], "Still here.")


class ClientStreaming(unittest.TestCase):
    def reply(self, streaming_chunks):
        response = lines(*streaming_chunks)
        response.ok = True
        return response

    def test_streaming_call_asks_ollama_to_stream_and_returns_the_whole_reply(self):
        client = OllamaClient()
        chunks = [{"message": {"content": "Four."}},
                  {"done": True, "prompt_eval_count": 10, "eval_count": 2}]
        pieces = []
        with patch("ai.ollama.requests.post", return_value=self.reply(chunks)) as post, \
             patch.object(client, "_log_placement"):
            result = client.generate_response("2+2?", [], on_text=pieces.append)
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        self.assertEqual(result, "Four.")
        self.assertEqual(pieces, ["Four."])
        self.assertEqual(client.last_stats["prompt_tokens"], 10)

    def test_without_a_callback_nothing_streams(self):
        client = OllamaClient()
        response = MagicMock()
        response.ok = True
        response.json.return_value = {"message": {"content": "Four."}}
        with patch("ai.ollama.requests.post", return_value=response) as post, \
             patch.object(client, "_log_placement"):
            client.generate_response("2+2?", [])
        self.assertFalse(post.call_args.kwargs["json"]["stream"])

    def test_the_switch_turns_streaming_off(self):
        client = OllamaClient()
        response = MagicMock()
        response.ok = True
        response.json.return_value = {"message": {"content": "Four."}}
        with patch.dict("os.environ", {"NEXUS_STREAM": "0"}), \
             patch("ai.ollama.requests.post", return_value=response) as post, \
             patch.object(client, "_log_placement"):
            result = client.generate_response("2+2?", [], on_text=lambda p: None)
        self.assertFalse(post.call_args.kwargs["json"]["stream"])
        self.assertEqual(result, "Four.")

    def test_connection_failure_gives_the_usual_message(self):
        client = OllamaClient()
        with patch("ai.ollama.requests.post",
                   side_effect=requests.exceptions.ConnectionError()):
            result = client.generate_response("hi", [], on_text=lambda p: None)
        self.assertEqual(result, "I can't connect to Ollama.")


class Options(unittest.TestCase):
    def test_defaults_leave_cpu_and_gpu_to_ollama(self):
        with patch.dict("os.environ", {}, clear=True):
            options = model_options()
        self.assertEqual(set(options), {"temperature", "top_p"})
        self.assertTrue(streaming_enabled())

    def test_threads_and_gpu_layers_are_passed_only_when_set(self):
        with patch.dict("os.environ", {"NEXUS_NUM_THREAD": "4", "NEXUS_NUM_GPU": "0"}):
            options = model_options()
        self.assertEqual(options["num_thread"], 4)
        self.assertEqual(options["num_gpu"], 0)

    def test_junk_values_are_ignored(self):
        with patch.dict("os.environ", {"NEXUS_NUM_THREAD": "fast; rm -rf"}):
            self.assertNotIn("num_thread", model_options())

    def test_placement_wording(self):
        name = "qwen2.5:3b"
        self.assertEqual(placement_text([{"name": name, "size": 100, "size_vram": 0}], name), "100% CPU")
        self.assertEqual(placement_text([{"name": name, "size": 100, "size_vram": 100}], name), "100% GPU")
        self.assertEqual(placement_text([{"name": name, "size": 100, "size_vram": 60}], name), "40% CPU / 60% GPU")
        self.assertIsNone(placement_text([], name))


class HistoryBudget(unittest.TestCase):
    def messages(self, count, size=400):
        out = [{"role": "system", "content": "prompt"}]
        for i in range(count):
            out.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"{i}:" + "x" * size})
        return out

    def test_older_messages_are_trimmed_to_the_budget_newest_first(self):
        result, info = compact_history(self.messages(20), old_budget=1200)
        contents = [m["content"] for m in result]
        self.assertGreater(info["dropped"], 0)
        self.assertEqual(result[0]["role"], "system")
        # the 6 most recent are always kept in full
        self.assertEqual(contents[-1][:3], "19:")
        self.assertEqual(sum(1 for c in contents if c.startswith("14:")), 1)
        # oldest ones went first
        self.assertFalse(any(c.startswith("0:") for c in contents))

    def test_nothing_is_dropped_when_it_fits(self):
        _, info = compact_history(self.messages(8, size=100))
        self.assertEqual(info["dropped"], 0)

    def test_the_input_list_is_never_changed(self):
        original = self.messages(20)
        before = json.dumps(original)
        compact_history(original, old_budget=500)
        self.assertEqual(json.dumps(original), before)

    def test_full_history_override_keeps_everything(self):
        with patch.dict("os.environ", {"NEXUS_FULL_HISTORY": "1"}):
            result, info = compact_history(self.messages(20), old_budget=500)
        self.assertEqual(len(result), 21)
        self.assertEqual(info["dropped"], 0)


class Presenter(unittest.TestCase):
    def run_stream(self, pieces, refine=None):
        written, speaker = [], MagicMock()
        presenter = StreamPresenter(speaker, refine or (lambda t: t.strip()), written.append)
        for piece in pieces:
            presenter.feed(piece)
        presenter.finish()
        return presenter, "".join(written), speaker

    def test_text_appears_in_order_with_spacing_kept(self):
        _, text, _ = self.run_stream(["The sky is blue. Gra", "ss is green.\n\nBye now."])
        self.assertEqual(text, "\nNEXUS: The sky is blue. Grass is green.\n\nBye now.\n")

    def test_first_sentence_is_spoken_early_and_the_rest_is_left(self):
        presenter, _, speaker = self.run_stream(["The sky is really blue. Grass is green."])
        speaker.speak.assert_called_once_with("The sky is really blue.", quiet=True)
        self.assertTrue(presenter.spoke_early)
        self.assertEqual(presenter.unspoken(), "Grass is green.")

    def test_a_one_sentence_reply_is_not_spoken_early(self):
        presenter, text, speaker = self.run_stream(["The sky is blue today."])
        speaker.speak.assert_not_called()
        self.assertFalse(presenter.spoke_early)
        self.assertTrue(presenter.displayed)
        self.assertIn("The sky is blue today.", text)

    def test_very_short_openers_are_not_spoken_alone(self):
        presenter, _, speaker = self.run_stream(["Sure. Here is the longer answer for you."])
        speaker.speak.assert_not_called()

    def test_refined_away_text_is_not_shown(self):
        presenter, text, _ = self.run_stream(
            ["Certainly! The answer is four."],
            refine=lambda t: t.replace("Certainly!", "").strip())
        self.assertNotIn("Certainly", text)
        self.assertIn("The answer is four.", text)

    def test_empty_reply_shows_nothing(self):
        presenter, text, _ = self.run_stream([])
        self.assertFalse(presenter.displayed)
        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
