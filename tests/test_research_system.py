import tempfile
import unittest
from pathlib import Path

from research.store import ResearchStore
from research.pipeline import ResearchPipeline


class FakeLLM:
    def generate_response(self, message, context=None):
        return "Overview\n\nKey findings\n\nOpen questions"


class ResearchStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.store = ResearchStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def test_session_source_and_topic_knowledge_persist(self):
        session = self.store.create_session("robotics", "Research robotics")
        source_id = self.store.save_source(session, {
            "url": "https://example.org/robotics",
            "title": "Robotics research",
            "publisher": "Example Institute",
            "content": "Robotics research " * 100,
            "relevance_score": 0.8,
        })
        self.assertIsNotNone(source_id)
        self.store.update_topic_knowledge("robotics", "Robotics summary", ["Cost"])
        topic = self.store.get_topic_knowledge("robotics")
        self.assertEqual(topic["summary"], "Robotics summary")
        self.assertEqual(topic["open_questions"], ["Cost"])

    def test_monitoring_requires_explicit_approval(self):
        self.store.add_monitored_topic("robotics", approved=False)
        topic = self.store.list_monitored_topics()[0]
        self.assertEqual(topic["approved"], 0)
        self.assertEqual(topic["enabled"], 0)

    def test_pipeline_filters_empty_and_unrelated_pages(self):
        pipeline = ResearchPipeline(FakeLLM(), self.db_path)
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "robotics",
                "Research robotics",
                [{
                    "url": "https://example.org/robotics",
                    "title": "Robotics research",
                    "source": "example.org",
                    "content": ("Robotics research and robotic systems. " * 100),
                }, {
                    "url": "https://example.net/cooking",
                    "title": "Cooking recipes",
                    "source": "example.net",
                    "content": ("Cooking recipes and ingredients. " * 100),
                }]
            )
            self.assertTrue(summary)
            self.assertIsNotNone(session_id)
            self.assertGreaterEqual(accepted, 1)
        finally:
            pipeline.close()


if __name__ == "__main__":
    unittest.main()
