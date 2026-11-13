import json
import sys
import unittest
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from ai.ollama import (
    OllamaClient,
    is_failure,
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

    def test_a_finished_stream_is_not_marked_incomplete(self):
        data = read_stream(lines({"message": {"content": "Done."}}, {"done": True}),
                           lambda piece: None)
        self.assertFalse(data["incomplete"])

    def test_a_stream_that_never_says_done_is_incomplete(self):
        data = read_stream(lines({"message": {"content": "Cut"}}), lambda piece: None)
        self.assertTrue(data["incomplete"])

    def test_a_broken_stream_is_marked_incomplete(self):
        response = MagicMock()
        def broken():
            yield json.dumps({"message": {"content": "Half an"}}).encode()
            raise requests.exceptions.ConnectionError("reset")
        response.iter_lines.return_value = broken()
        self.assertTrue(read_stream(response, lambda piece: None)["incomplete"])

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

    def test_the_client_reports_a_cut_off_reply(self):
        client = OllamaClient()
        response = self.reply([{"message": {"content": "Half"}}])
        with patch("ai.ollama.requests.post", return_value=response), \
             patch.object(client, "_log_placement"):
            client.generate_response("hi", [], on_text=lambda p: None)
        self.assertTrue(client.last_stats.get("incomplete"))

    def test_a_finished_reply_is_not_reported_as_cut_off(self):
        client = OllamaClient()
        response = self.reply([{"message": {"content": "Whole."}}, {"done": True}])
        with patch("ai.ollama.requests.post", return_value=response), \
             patch.object(client, "_log_placement"):
            client.generate_response("hi", [], on_text=lambda p: None)
        self.assertFalse(client.last_stats.get("incomplete"))

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
    def test_client_defaults_to_qwen_3b(self):
        self.assertEqual(OllamaClient().model, "qwen2.5:3b")

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
        # The newest two messages remain in the recent window. Older
        # messages are retained newest-first within the character budget.
        self.assertEqual(contents[-1][:3], "19:")
        self.assertEqual(contents[-2][:3], "18:")
        self.assertEqual(sum(1 for c in contents if c.startswith("15:")), 1)
        self.assertEqual(sum(1 for c in contents if c.startswith("16:")), 1)
        self.assertEqual(sum(1 for c in contents if c.startswith("17:")), 1)
        self.assertFalse(any(c.startswith("14:") for c in contents))
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


class FailureMessages(unittest.TestCase):
    def test_every_client_error_message_is_recognised(self):
        for text in ["Ollama error (HTTP 500)", "Ollama error: boom",
                     "Ollama returned an invalid response.",
                     "Ollama returned an empty response.",
                     "Ollama took too long to respond.",
                     "Ollama request error: x", "I can't connect to Ollama."]:
            self.assertTrue(is_failure(text), text)

    def test_normal_replies_are_not_failures(self):
        for text in ["", None, "Four.", "Ollama is a tool for running models."]:
            self.assertFalse(is_failure(text), text)

    def test_a_dropped_connection_keeps_the_text_already_received(self):
        response = MagicMock()
        def dropped():
            yield json.dumps({"message": {"content": "Half an answer"}}).encode()
            raise requests.exceptions.ConnectionError("reset")
        response.iter_lines.return_value = dropped()
        data = read_stream(response, lambda piece: None)
        self.assertEqual(data["message"]["content"], "Half an answer")

    def test_a_dropped_connection_with_no_text_still_raises(self):
        response = MagicMock()
        def dropped():
            raise requests.exceptions.ConnectionError("reset")
            yield
        response.iter_lines.return_value = dropped()
        with self.assertRaises(requests.exceptions.ConnectionError):
            read_stream(response, lambda piece: None)


class _StubModule(ModuleType):
    """A stand-in for a package that is missing or unusable on this machine."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []
        self.__spec__ = ModuleSpec(name, None, is_package=True)

    def __getattr__(self, attribute):
        if attribute.startswith("__"):
            raise AttributeError(attribute)
        value = MagicMock(name=f"{self.__name__}.{attribute}")
        setattr(self, attribute, value)
        return value


def _stub(name):
    sys.modules[name] = _StubModule(name)


def load_assistant_class():
    """
    Import core.assistant on a machine without the Windows-only and audio
    packages by standing in for whichever ones are missing.
    """

    import importlib
    from types import ModuleType

    stubbed = []

    # Installed but unusable here (no audio hardware library, or Windows only).
    for name in ("sounddevice", "pynput", "pynput.keyboard", "winsound"):
        try:
            importlib.import_module(name)
        except Exception:
            _stub(name)

    for _ in range(40):
        try:
            return importlib.import_module("core.assistant").NexusAssistant
        except ModuleNotFoundError as error:
            name = error.name
            if not name or name in sys.modules:
                raise
            _stub(name)
            stubbed.append(name)
            sys.modules.pop("core.assistant", None)

    raise ImportError("could not stub the missing modules")


class Shutdown(unittest.TestCase):
    def assistant(self):
        NexusAssistant = load_assistant_class()
        a = NexusAssistant.__new__(NexusAssistant)
        for name in ("conversation", "memory", "knowledge", "observer",
                     "language_learner", "tool_registry", "action_history"):
            setattr(a, name, MagicMock())
        return a

    def test_every_database_is_closed(self):
        a = self.assistant()
        a.shutdown()
        a.conversation.close.assert_called_once()
        a.memory.db.close.assert_called_once()
        a.knowledge.close.assert_called_once()
        a.observer.close.assert_called_once()
        a.language_learner.close.assert_called_once()
        a.action_history.close.assert_called_once()
        a.tool_registry.get.return_value.research_pipeline.close.assert_called_once()

    def test_one_failure_does_not_stop_the_rest(self):
        a = self.assistant()
        a.conversation.close.side_effect = RuntimeError("locked")
        a.memory.db.close.side_effect = RuntimeError("locked")
        a.shutdown()
        a.knowledge.close.assert_called_once()
        a.language_learner.close.assert_called_once()

    def test_calling_it_twice_closes_once(self):
        a = self.assistant()
        a.shutdown()
        a.shutdown()
        a.observer.close.assert_called_once()

    def test_main_calls_it_even_after_an_error(self):
        load_assistant_class()
        import main
        assistant = MagicMock()
        assistant.start.side_effect = RuntimeError("boom")
        with patch.object(main, "NexusAssistant", return_value=assistant), \
             patch.object(main, "animation"), patch.object(main, "clear_status"), \
             patch("builtins.print"):
            main.main()
        assistant.shutdown.assert_called_once()


class ChatPathWithStreaming(unittest.TestCase):
    """_process_input's general chat branch, with everything else stubbed."""

    def assistant(self, pieces, reply):
        NexusAssistant = load_assistant_class()
        a = NexusAssistant.__new__(NexusAssistant)
        for name in ("conversation", "language_learner", "input_manager", "speaker",
                     "memory", "intent_fast", "llm", "intent", "observer"):
            setattr(a, name, MagicMock())
        a.language_learner.observe.return_value = None
        a.intent_fast.builtin_command.return_value = None
        a.intent_fast.is_exit_request.return_value = False
        a.intent.resolve.return_value = MagicMock(success=False, message="")
        a.conversation.get_context.return_value = []
        a.input_manager.last_input_was_voice = False
        a.memory.process_memory.return_value = None
        a.response_style = MagicMock()
        a.response_style.refine.side_effect = lambda t: t.replace("Certainly! ", "").strip()
        a.check_memory = lambda text: None
        a.get_relevant_knowledge = lambda text: ""
        a.response_displayed = False
        def generate(text, context, on_text=None):
            for piece in pieces:
                on_text and on_text(piece)
            return reply
        a.llm.generate_response.side_effect = generate
        return a

    def test_streamed_reply_is_shown_once_and_stored_whole(self):
        text = "Certainly! The sky is really blue. Grass is green today."
        a = self.assistant([text[:20], text[20:]], text)
        with patch("sys.stdout"):
            result = a._process_input("tell me about colours")
        self.assertEqual(result, "The sky is really blue. Grass is green today.")
        self.assertTrue(a.response_displayed)
        a.conversation.add_assistant_message.assert_called_once_with(result)
        a.memory.save_conversation.assert_called_once_with("tell me about colours", result)

    def test_the_spoken_remainder_is_cleaned_like_the_screen_text(self):
        text = "The sky is really blue. Certainly! Grass is green today."
        a = self.assistant([text], text)
        with patch("sys.stdout"):
            a._process_input("tell me about colours")
        spoken = [c.args[0] for c in a.speaker.speak.call_args_list]
        self.assertEqual(spoken, ["The sky is really blue.", "Grass is green today."])

    def test_a_one_sentence_reply_is_spoken_once_in_full(self):
        a = self.assistant(["Four is the answer."], "Four is the answer.")
        with patch("sys.stdout"):
            a._process_input("2+2")
        a.speaker.speak.assert_called_once_with("Four is the answer.")

    def test_an_error_is_left_for_the_main_loop_to_print(self):
        a = self.assistant(["Half an"], "Ollama took too long to respond.")
        with patch("sys.stdout"):
            a._process_input("hi")
        self.assertFalse(a.response_displayed)

    def test_a_cut_off_reply_is_shown_flagged_and_never_stored_or_spoken(self):
        a = self.assistant(["The sky is really blue. Grass is"], "The sky is really blue. Grass is")
        a.llm.last_stats = {"incomplete": True}
        with patch("sys.stdout"):
            result = a._process_input("tell me about colours")
        self.assertIn("cut off", result)
        self.assertTrue(a.response_displayed)
        a.conversation.add_assistant_message.assert_not_called()
        a.memory.save_conversation.assert_not_called()
        # only the first sentence, spoken while streaming, was ever voiced
        spoken = [c.args[0] for c in a.speaker.speak.call_args_list]
        self.assertEqual(spoken, ["The sky is really blue."])

    def test_error_messages_are_not_saved_as_conversation(self):
        a = self.assistant([], "I can't connect to Ollama.")
        with patch.dict("os.environ", {"NEXUS_STREAM": "0"}):
            # Use a normal question so the greeting fast path does not
            # bypass the mocked model error.
            result = a._process_input("tell me about colours")
        self.assertEqual(result, "I can't connect to Ollama.")
        a.conversation.add_assistant_message.assert_not_called()
        a.memory.save_conversation.assert_not_called()
        a.speaker.speak.assert_called_once_with("I can't connect to Ollama.")

    def test_streaming_off_behaves_as_before(self):
        a = self.assistant([], "Four is the answer.")
        with patch.dict("os.environ", {"NEXUS_STREAM": "0"}):
            a._process_input("2+2")
        self.assertFalse(a.response_displayed)
        a.speaker.speak.assert_called_once_with("Four is the answer.")


if __name__ == "__main__":
    unittest.main()
