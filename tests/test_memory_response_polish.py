import unittest
from unittest.mock import MagicMock

from core.assistant import NexusAssistant


class GroundedMemoryAnswerPolishTests(unittest.TestCase):

    def setUp(self):
        self.assistant = NexusAssistant.__new__(NexusAssistant)
        self.assistant.llm = MagicMock()
        self.assistant.conversation = MagicMock()
        self.assistant.speaker = MagicMock()

    def test_raw_memory_answer_is_sent_to_ollama_for_polishing(self):
        raw = (
            "You told me: drawing and sculpting with clay. "
            "I don't have a separate stored detail about cubing."
        )
        polished = (
            "You told me you enjoy drawing and sculpting with clay. "
            "I don't have a separate stored detail about cubing."
        )
        self.assistant.llm.generate_response.return_value = polished

        result = self.assistant._deliver_grounded_memory_answer(raw)

        self.assertEqual(result, polished)
        args, kwargs = self.assistant.llm.generate_response.call_args
        self.assertIn(raw, args[0])
        instructions = kwargs["context"][0]["content"].lower()
        self.assertIn("authoritative evidence from sqlite", instructions)
        self.assertIn("do not add", instructions)
        self.assertIsNone(kwargs["on_text"])
        self.assistant.conversation.add_assistant_message.assert_called_once_with(
            polished
        )
        self.assistant.speaker.speak.assert_called_once_with(polished)

    def test_ollama_failure_returns_the_original_grounded_answer(self):
        raw = "NEXUS is a project. Its purpose is not established."
        self.assistant.llm.generate_response.return_value = (
            "Ollama error (connection unavailable)"
        )

        result = self.assistant._polish_grounded_memory_answer(raw)

        self.assertEqual(result, raw)

    def test_ollama_exception_returns_the_original_grounded_answer(self):
        raw = "You mentioned badminton."
        self.assistant.llm.generate_response.side_effect = RuntimeError(
            "Ollama unavailable"
        )

        result = self.assistant._polish_grounded_memory_answer(raw)

        self.assertEqual(result, raw)


if __name__ == "__main__":
    unittest.main()
