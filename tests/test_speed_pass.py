import unittest
from unittest.mock import MagicMock, patch

from ai.ollama import (
    DEFAULT_KEEP_ALIVE,
    OLD_MESSAGE_MAX_CHARS,
    RECENT_MESSAGE_MAX_CHARS,
    OllamaClient,
    RECENT_FULL_MESSAGES,
    compact_history,
    extract_stats,
    format_stats,
    get_keep_alive
)


NANOSECONDS_PER_SECOND = 1_000_000_000


def fake_response(extra=None, ok=True):
    response = MagicMock()
    response.ok = ok
    response.status_code = 200 if ok else 500
    response.text = ""
    data = {"message": {"content": "Understood."}}
    data.update(extra or {})
    response.json.return_value = data
    return response


def send(message, context=None, observer=None, response=None):
    """Run one request through OllamaClient with a fake Ollama server."""
    client = OllamaClient(observer=observer)

    with patch(
        "ai.ollama.requests.post",
        return_value=response or fake_response()
    ) as post:
        client.generate_response(message, context)

    return client, post.call_args.kwargs["json"]


class KeepAliveTests(unittest.TestCase):
    def test_request_asks_ollama_to_keep_the_model_loaded(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("NEXUS_OLLAMA_KEEP_ALIVE", None)
            _, payload = send("hello")

        self.assertEqual(payload["keep_alive"], DEFAULT_KEEP_ALIVE)

    def test_keep_alive_can_be_changed_with_environment_variable(self):
        with patch.dict("os.environ", {"NEXUS_OLLAMA_KEEP_ALIVE": "1h"}):
            self.assertEqual(get_keep_alive(), "1h")
            _, payload = send("hello")

        self.assertEqual(payload["keep_alive"], "1h")

    def test_blank_setting_falls_back_to_default(self):
        with patch.dict("os.environ", {"NEXUS_OLLAMA_KEEP_ALIVE": "  "}):
            self.assertEqual(get_keep_alive(), DEFAULT_KEEP_ALIVE)


class ConversationMemoryIsUntouchedTests(unittest.TestCase):
    def long_conversation(self):
        long_brief = "Research brief sentence. " * 400
        context = []
        for index in range(10):
            context.append({"role": "user", "content": f"question {index}"})
            context.append(
                {
                    "role": "assistant",
                    "content": long_brief if index in (2, 9) else f"answer {index}"
                }
            )
        context.append({"role": "user", "content": "latest question"})
        return context, long_brief

    def test_recent_messages_are_bounded_without_changing_stored_history(self):
        context, long_brief = self.long_conversation()
        snapshot = [dict(item) for item in context]

        _, payload = send("latest question", context)

        sent = payload["messages"]

        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(len(sent) - 1, len(context))
        # Keep the latest user message intact, but bound a huge recent reply.
        self.assertEqual(sent[-1], context[-1])
        self.assertLessEqual(
            len(sent[-2]["content"]),
            RECENT_MESSAGE_MAX_CHARS
        )
        self.assertNotIn(long_brief, [item["content"] for item in sent])
        self.assertEqual(context, snapshot)

    def test_old_long_messages_are_shortened_for_the_model_only(self):
        context, long_brief = self.long_conversation()
        snapshot = [dict(item) for item in context]

        client, payload = send("latest question", context)

        sent_texts = [item["content"] for item in payload["messages"][1:]]
        old_long = sent_texts[5]  # the long reply from turn 2

        self.assertLess(len(old_long), OLD_MESSAGE_MAX_CHARS)
        self.assertTrue(long_brief.startswith(old_long.split(" ...")[0][:100]))
        self.assertEqual(client.last_stats["history_shortened"], 2)
        self.assertGreater(client.last_stats["history_chars_saved"], 10000)
        # The stored conversation passed in is not touched.
        self.assertEqual(context, snapshot)

    def test_short_old_messages_are_never_shortened(self):
        context, _ = self.long_conversation()

        _, payload = send("latest question", context)

        sent_texts = [item["content"] for item in payload["messages"][1:]]

        self.assertEqual(sent_texts[0], "question 0")
        self.assertEqual(sent_texts[1], "answer 0")

    def test_full_history_can_be_switched_back_on(self):
        context, _ = self.long_conversation()

        with patch.dict("os.environ", {"NEXUS_FULL_HISTORY": "1"}):
            _, payload = send("latest question", context)

        self.assertEqual(payload["messages"][1:], context)

    def test_reference_context_messages_are_kept(self):
        context = [
            {"role": "system", "content": "Stored knowledge: " + "x" * 5000},
            {"role": "system", "content": "Language profile: Rohan"},
            {"role": "user", "content": "follow up"}
        ]

        _, payload = send("follow up", context)

        self.assertEqual(payload["messages"][1:], context)

    def test_no_context_options_are_added(self):
        _, payload = send("hello")

        self.assertNotIn("num_ctx", payload["options"])
        self.assertNotIn("num_predict", payload["options"])


class CompactHistoryTests(unittest.TestCase):
    def test_system_reference_material_is_never_shortened(self):
        reference = {"role": "system", "content": "Stored knowledge: " + "x" * 6000}
        messages = [
            {"role": "system", "content": "prompt"},
            reference,
            {"role": "user", "content": "hi"}
        ]

        result, info = compact_history(messages)

        self.assertEqual(result, messages)
        self.assertEqual(info["shortened"], 0)

    def test_old_long_user_messages_are_shortened_too(self):
        messages = [{"role": "system", "content": "prompt"}]
        messages.append({"role": "user", "content": "word " * 600})
        for index in range(RECENT_FULL_MESSAGES):
            messages.append({"role": "assistant", "content": f"reply {index}"})

        result, info = compact_history(messages)

        self.assertEqual(info["shortened"], 1)
        self.assertLess(len(result[1]["content"]), OLD_MESSAGE_MAX_CHARS)

    def test_a_long_recent_assistant_message_is_shortened(self):
        messages = [
            {"role": "system", "content": "prompt"},
            {"role": "assistant", "content": "word " * 600},
            {"role": "user", "content": "follow up"}
        ]

        result, info = compact_history(messages)

        self.assertEqual(result[-1], messages[-1])
        self.assertLessEqual(
            len(result[1]["content"]),
            RECENT_MESSAGE_MAX_CHARS
        )
        self.assertEqual(info["shortened"], 1)


class ExtractStatsTests(unittest.TestCase):
    def test_converts_nanoseconds_to_milliseconds(self):
        data = {
            "load_duration": 2 * NANOSECONDS_PER_SECOND,
            "prompt_eval_count": 1800,
            "prompt_eval_duration": 3_500_000_000,
            "eval_count": 85,
            "eval_duration": 9_000_000_000,
            "total_duration": 14_500_000_000
        }
        messages = [
            {"role": "system", "content": "abcd"},
            {"role": "user", "content": "hello"}
        ]

        stats = extract_stats(data, messages)

        self.assertEqual(stats["load_ms"], 2000.0)
        self.assertEqual(stats["prompt_tokens"], 1800)
        self.assertEqual(stats["prompt_eval_ms"], 3500.0)
        self.assertEqual(stats["generated_tokens"], 85)
        self.assertEqual(stats["generation_ms"], 9000.0)
        self.assertEqual(stats["ollama_total_ms"], 14500.0)
        self.assertEqual(stats["messages_sent"], 2)
        self.assertEqual(stats["prompt_chars"], 9)

    def test_missing_fields_are_left_out(self):
        stats = extract_stats({}, [{"role": "user", "content": "hi"}])

        self.assertEqual(
            stats,
            {"messages_sent": 1, "prompt_chars": 2}
        )

    def test_format_stats_is_readable(self):
        line = format_stats(
            {
                "load_ms": 2000.0,
                "prompt_tokens": 1800,
                "prompt_eval_ms": 3500.0,
                "generated_tokens": 85,
                "generation_ms": 9000.0,
                "ollama_total_ms": 14500.0
            }
        )

        self.assertEqual(
            line,
            "load 2.0s | prompt 1800 tokens in 3.5s | "
            "generated 85 tokens in 9.0s | total 14.5s"
        )

    def test_format_stats_handles_no_data(self):
        self.assertEqual(format_stats({}), "")


class TimingsAreRecordedTests(unittest.TestCase):
    def test_timings_are_saved_without_message_text(self):
        observer = MagicMock()
        response = fake_response(
            {
                "load_duration": NANOSECONDS_PER_SECOND,
                "prompt_eval_count": 500,
                "prompt_eval_duration": 2 * NANOSECONDS_PER_SECOND,
                "eval_count": 40,
                "eval_duration": 4 * NANOSECONDS_PER_SECOND,
                "total_duration": 7 * NANOSECONDS_PER_SECOND
            }
        )
        secret = "my private question about something personal"

        client, _ = send(secret, observer=observer, response=response)

        metadata = observer.record_event.call_args.kwargs["metadata"]

        self.assertEqual(metadata["load_ms"], 1000.0)
        self.assertEqual(metadata["prompt_tokens"], 500)
        self.assertEqual(metadata["generated_tokens"], 40)
        self.assertEqual(metadata["model"], client.model)
        self.assertIn("input_length", metadata)
        self.assertIn("output_length", metadata)

        for value in metadata.values():
            self.assertNotIn(secret, str(value))
            self.assertNotIn("Understood.", str(value))

    def test_failed_request_does_not_reuse_old_timings(self):
        observer = MagicMock()
        client = OllamaClient(observer=observer)

        good = fake_response({"eval_count": 12})
        with patch("ai.ollama.requests.post", return_value=good):
            client.generate_response("first")

        bad = fake_response(ok=False)
        with patch("ai.ollama.requests.post", return_value=bad):
            client.generate_response("second")

        metadata = observer.record_event.call_args.kwargs["metadata"]

        self.assertNotIn("generated_tokens", metadata)
        self.assertNotIn("messages_sent", metadata)
        self.assertEqual(
            observer.record_event.call_args.kwargs["status"],
            "failed"
        )


if __name__ == "__main__":
    unittest.main()
