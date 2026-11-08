import unittest
from unittest.mock import MagicMock, patch

from ai.ollama import OllamaClient
from tools.application import ApplicationTool, contains_phrase


class ContainsPhraseTests(unittest.TestCase):
    def test_matches_whole_words_only(self):
        self.assertTrue(contains_phrase("open idle", "idle"))
        self.assertTrue(contains_phrase("open python idle now", "idle"))
        self.assertFalse(contains_phrase("open the middle file", "idle"))
        self.assertFalse(contains_phrase("start calculating", "calc"))

    def test_matches_multi_word_phrases(self):
        self.assertTrue(
            contains_phrase("open files and docs", "files and docs")
        )


class ApplicationMatchingTests(unittest.TestCase):
    def setUp(self):
        self.tool = ApplicationTool()

    def test_known_commands_are_still_handled(self):
        for command in [
            "open spotify",
            "launch notepad",
            "open calculator",
            "open calc",
            "open microsoft word",
            "start excel",
            "open downloads",
            "open file explorer",
            "open python idle"
        ]:
            with self.subTest(command=command):
                self.assertTrue(self.tool.can_handle(command))

    def test_names_inside_other_words_are_ignored(self):
        for command in [
            "open the middle section of the report",
            "start calculating the total",
            "run the downloader script"
        ]:
            with self.subTest(command=command):
                self.assertFalse(self.tool.can_handle(command))

    def test_requires_a_launch_verb(self):
        self.assertFalse(self.tool.can_handle("what is spotify"))


class OllamaMessageTests(unittest.TestCase):
    def _send(self, message, context):
        fake_response = MagicMock()
        fake_response.ok = True
        fake_response.json.return_value = {
            "message": {"content": "Understood."}
        }

        with patch("ai.ollama.requests.post", return_value=fake_response) as post:
            client = OllamaClient()
            client.generate_response(message, context)

        return post.call_args.kwargs["json"]["messages"]

    def test_current_message_is_sent_once(self):
        context = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Hello."},
            {"role": "user", "content": "what time is it"}
        ]

        messages = self._send("what time is it", context)

        matches = [
            m for m in messages
            if m["role"] == "user" and m["content"] == "what time is it"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(messages[-1]["content"], "what time is it")

    def test_current_message_is_added_when_missing_from_context(self):
        messages = self._send("what time is it", [])

        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "what time is it")

    def test_repeated_question_later_in_conversation_is_kept(self):
        context = [
            {"role": "user", "content": "status"},
            {"role": "assistant", "content": "All systems normal."},
            {"role": "user", "content": "status"}
        ]

        messages = self._send("status", context)

        matches = [
            m for m in messages
            if m["role"] == "user" and m["content"] == "status"
        ]
        self.assertEqual(len(matches), 2)

    def test_only_one_system_prompt_is_sent(self):
        messages = self._send(
            "hi",
            [{"role": "user", "content": "hi"}]
        )

        self.assertEqual(
            len([m for m in messages if m["role"] == "system"]),
            1
        )


if __name__ == "__main__":
    unittest.main()
