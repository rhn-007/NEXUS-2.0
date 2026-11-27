import unittest

from tools.research import ResearchTool


class ResearchInputTests(unittest.TestCase):
    def test_extract_topic_preserves_detailed_research_scope(self):
        request = (
            "Research the development of autonomous vehicles, their applications "
            "in transportation and logistics, the technologies that make them work, "
            "their major safety and technical challenges, and their future impact "
            "on society. Save the important findings."
        )
        tool = object.__new__(ResearchTool)

        topic = tool._extract_topic(request)

        self.assertGreater(len(topic), 150)
        self.assertIn("transportation and logistics", topic)
        self.assertIn("safety and technical challenges", topic)
        self.assertNotIn("Save the important findings", topic)

    def test_research_topic_accepts_requests_longer_than_150_characters(self):
        topic = (
            "autonomous vehicles and their applications in transportation and "
            "logistics, enabling technologies, safety and technical challenges, "
            "and their future impact on society"
        )
        tool = object.__new__(ResearchTool)
        received = []

        def collect_pages(value):
            received.append(value)
            return []

        tool._collect_pages = collect_pages

        response = tool.research_topic(topic)

        self.assertEqual(received, [topic])
        self.assertFalse(response.success)
        self.assertNotIn("150 characters", response.message)
        self.assertIn("couldn't extract usable research pages", response.message)


if __name__ == "__main__":
    unittest.main()
