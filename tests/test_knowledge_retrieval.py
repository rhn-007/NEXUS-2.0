import unittest
from unittest.mock import MagicMock

from tests.test_streaming import load_assistant_class


class SavedResearchRetrieval(unittest.TestCase):
    def setUp(self):
        assistant_class = load_assistant_class()
        self.assistant = assistant_class.__new__(assistant_class)
        self.assistant.knowledge = MagicMock()

    def test_extracts_topic_without_follow_up_instructions(self):
        request = (
            "Retrieve my previous research on artificial intelligence as a field.\n"
            "Give me the important findings from the saved entries."
        )
        self.assertEqual(
            self.assistant._extract_knowledge_topic(request),
            "artificial intelligence as a field",
        )

    def test_retrieves_matching_saved_entries_including_unverified_sources(self):
        self.assistant.knowledge.get_all_knowledge.return_value = [
            {
                "id": 46,
                "topic": "artificial intelligence as a field",
                "title": "AI Fields and Their Applications",
                "content": "Artificial intelligence enables systems to perform tasks "
                           "that normally require human intelligence. Machine learning "
                           "and deep learning are important areas of AI.",
                "source_name": "Neural Concept",
                "source_url": "https://example.com/ai",
                "verification_status": "unverified",
            },
            {
                "id": 45,
                "topic": "artificial intelligence as a field",
                "title": "Branches of Artificial Intelligence",
                "content": "Machine learning uses data to improve system performance.",
                "source_name": "GeeksforGeeks",
                "source_url": "https://example.com/ml",
                "verification_status": "unverified",
            },
            {
                "id": 44,
                "topic": "summarization tools",
                "title": "AI Text Summarizer",
                "content": "This is unrelated content.",
                "source_name": "Example",
                "source_url": "https://example.com/summary",
                "verification_status": "unverified",
            },
        ]

        result = self.assistant.retrieve_saved_research(
            "Retrieve my previous research on artificial intelligence as a field. "
            "Give me the important findings from the saved entries."
        )

        self.assertIn("Your saved research on artificial intelligence as a field", result)
        self.assertIn("Found 2 saved source entries.", result)
        self.assertIn("AI Fields and Their Applications", result)
        self.assertIn("Branches of Artificial Intelligence", result)
        self.assertIn("Machine learning uses data", result)
        self.assertIn("Verification: unverified", result)
        self.assertNotIn("AI Text Summarizer", result)

    def test_does_not_return_entries_for_a_different_topic(self):
        self.assistant.knowledge.get_all_knowledge.return_value = [
            {
                "topic": "summarization tools",
                "title": "AI Text Summarizer",
                "content": "Unrelated saved content.",
                "source_name": "Example",
                "source_url": "https://example.com",
                "verification_status": "unverified",
            }
        ]

        result = self.assistant.retrieve_saved_research(
            "Retrieve my previous research on artificial intelligence as a field."
        )

        self.assertIn("couldn't find saved knowledge entries", result)
        self.assertNotIn("Unrelated saved content", result)

    def test_non_retrieval_requests_are_not_intercepted(self):
        self.assertIsNone(
            self.assistant.retrieve_saved_research(
                "Explain artificial intelligence as a field."
            )
        )


if __name__ == "__main__":
    unittest.main()
