import unittest
from unittest.mock import patch

from memory.memory_manager import MemoryManager


class ProjectHistoryAnswerTests(unittest.TestCase):

    def setUp(self):
        self.memory = MemoryManager.__new__(MemoryManager)

    def test_project_history_uses_only_user_authored_project_evidence(self):
        with patch.object(
            self.memory,
            "_facts_by_key",
            return_value={"project": ["NEXUS"]}
        ), patch.object(
            self.memory,
            "_recent_conversation_messages",
            return_value=[
                ("user", "NEXUS is a project I was working on."),
                ("assistant", "NEXUS is your Windows computer with 32 GB RAM."),
                ("user", "I use WhatsApp on my computer."),
                ("user", "What projects have I actually told you about?"),
            ]
        ):
            answer = self.memory.answer_project_history(
                "What projects have I actually told you about?"
            )

        self.assertIn("NEXUS", answer)
        self.assertIn("NEXUS is a project I was working on.", answer)
        self.assertIn("Purpose and additional features: not established", answer)
        self.assertNotIn("Windows computer", answer)
        self.assertNotIn("WhatsApp", answer)


    def test_project_name_is_recovered_from_explicit_transcript_when_fact_row_is_missing(self):
        with patch.object(
            self.memory,
            "_facts_by_key",
            return_value={}
        ), patch.object(
            self.memory,
            "_recent_conversation_messages",
            return_value=[
                ("user", "NEXUS is a project I was working on."),
                ("assistant", "NEXUS is your Windows computer."),
                ("user", "What projects have I actually told you about?"),
            ]
        ):
            answer = self.memory.answer_project_history(
                "What projects have I actually told you about?"
            )

        self.assertIn("NEXUS", answer)
        self.assertIn("NEXUS is a project I was working on.", answer)
        self.assertIn("Purpose and additional features: not established", answer)
        self.assertNotIn("Windows computer", answer)

    def test_project_history_does_not_infer_from_assistant_messages(self):
        with patch.object(
            self.memory,
            "_facts_by_key",
            return_value={"project": ["NEXUS"]}
        ), patch.object(
            self.memory,
            "_recent_conversation_messages",
            return_value=[
                ("assistant", "You built NEXUS as a badminton application."),
                ("user", "What projects have I built?"),
            ]
        ):
            answer = self.memory.answer_project_history(
                "What projects have I built?"
            )

        self.assertIn("don't have enough user-authored evidence", answer)
        self.assertNotIn("badminton", answer)

    def test_explicit_personal_ai_assistant_statement_establishes_project_purpose(self):
        with patch.object(
            self.memory,
            "_facts_by_key",
            return_value={"project": ["NEXUS"]}
        ), patch.object(
            self.memory,
            "_recent_conversation_messages",
            return_value=[
                (
                    "user",
                    "I have been working on a project called NEXUS which is you. "
                    "You are my personal AI assistant."
                ),
                (
                    "user",
                    "What projects have I actually told you that I have built?"
                ),
            ]
        ):
            answer = self.memory.answer_project_history(
                "What projects have I actually told you that I have built?"
            )

        self.assertIn("NEXUS", answer)
        self.assertIn("Purpose: Personal AI assistant.", answer)
        self.assertNotIn("Purpose and additional features: not established", answer)

    def test_non_project_question_is_not_handled(self):
        self.assertIsNone(
            self.memory.answer_project_history("What do you know about me?")
        )


if __name__ == "__main__":
    unittest.main()
