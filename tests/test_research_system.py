import tempfile
import unittest
from pathlib import Path

from research.store import ResearchStore
from research.pipeline import ResearchPipeline


class FakeLLM:
    def __init__(self, response=("Overview\nA concise overview grounded in the retrieved source material.\n\n"
                                  "Key findings\n- Robotics research develops systems for practical tasks [1].\n"
                                  "- Researchers investigate autonomous robotic capabilities [1].\n\n"
                                  "Evidence limitations\nThe available source provides limited coverage of this topic.\n\n"
                                  "Open questions\nFurther independent evidence is needed to assess broader impacts.")):
        self.response = response
        self.last_prompt = None

    def generate_response(self, message, context=None):
        self.last_prompt = message
        return self.response


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
        llm = FakeLLM()
        pipeline = ResearchPipeline(llm, self.db_path)
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
            self.assertLessEqual(len(llm.last_prompt), 5000)
        finally:
            pipeline.close()

    def test_pipeline_deduplicates_sources_and_rejects_listing_pages(self):
        llm = FakeLLM()
        pipeline = ResearchPipeline(llm, self.db_path)
        article = {
            "url": "https://example.org/robotics/article",
            "title": "Robotics research breakthrough",
            "source": "example.org",
            "content": ("Robotics systems are being developed for useful tasks. "
                        "Researchers tested autonomous robotic manipulation. " * 30),
        }
        duplicate = dict(article)
        duplicate["url"] = "https://mirror.example.org/copy"
        listing = {
            "url": "https://example.net/robotics",
            "title": "Latest News Archive",
            "source": "example.net",
            "content": ("Robotics news archive lists many recent robotics stories. "
                        "Robotics researchers publish updates and reports. " * 30),
        }
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "robotics", "Research robotics", [article, duplicate, listing]
            )
            self.assertTrue(summary)
            self.assertEqual(accepted, 1)
            rows = pipeline.store.connection.execute(
                "SELECT COUNT(*) FROM research_sources WHERE session_id=?",
                (session_id,)
            ).fetchone()[0]
            self.assertEqual(rows, 1)
        finally:
            pipeline.close()

    def test_pipeline_does_not_store_repetitive_low_quality_content(self):
        pipeline = ResearchPipeline(FakeLLM(), self.db_path)
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "robotics", "Research robotics", [{
                    "url": "https://example.org/robotics",
                    "title": "Robotics research",
                    "content": "robotics " * 500,
                }]
            )
            self.assertIsNone(summary)
            self.assertEqual(accepted, 0)
            status = pipeline.store.connection.execute(
                "SELECT status FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()["status"]
            self.assertEqual(status, "no_relevant_sources")
        finally:
            pipeline.close()

    def test_broad_request_requires_multiple_independent_publishers(self):
        pipeline = ResearchPipeline(FakeLLM(), self.db_path)
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "humanoid robots",
                "Research the development of humanoid robots, their real-world "
                "applications, current limitations, and future prospects. "
                "Save the important findings.",
                [{
                    "url": "https://example.org/humanoids",
                    "title": "Humanoid robot research",
                    "publisher": "Example Institute",
                    "content": ("Humanoid robots are being developed for useful tasks. "
                                "Researchers study humanoid robot mobility and manipulation. " * 30),
                }]
            )
            self.assertIsNone(summary)
            self.assertEqual(accepted, 1)
            session = pipeline.store.connection.execute(
                "SELECT status, metadata_json FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()
            self.assertEqual(session["status"], "partial")
            self.assertIn(
                "too_few_independent_publishers_for_broad_request",
                session["metadata_json"]
            )
            self.assertIsNone(pipeline.store.get_topic_knowledge("humanoid robots"))
        finally:
            pipeline.close()

    def test_broad_request_can_complete_with_independent_publishers(self):
        broad_summary = (
            "Overview\nHumanoid robotics is an active area of engineering research.\n\n"
            "Requested aspects coverage\n"
            "- Development: SUPPORTED by the supplied research [1].\n"
            "- Real-world applications: SUPPORTED by deployment research [2].\n"
            "- Current limitations: SUPPORTED by engineering evaluations [2].\n"
            "- Future prospects: SUPPORTED by the research outlook [1].\n\n"
            "Key findings\n"
            "- Research explores humanoid mobility and manipulation [1].\n"
            "- Evaluations examine safety and task performance [2].\n\n"
            "Evidence limitations\nThe available sources cover the requested aspects, "
            "but conclusions remain limited to these publications.\n\n"
            "Open questions\nLong-term performance requires further independent study."
        )
        pipeline = ResearchPipeline(FakeLLM(broad_summary), self.db_path)
        try:
            pages = [
                {
                    "url": "https://example.org/humanoids",
                    "title": "Humanoid robot research",
                    "publisher": "Example Institute",
                    "content": ("Humanoid robots are being developed for useful tasks. "
                                "Researchers study humanoid robot mobility and manipulation. " * 30),
                },
                {
                    "url": "https://research.example.net/humanoids",
                    "title": "Humanoid robotics applications",
                    "publisher": "Research Example",
                    "content": ("Humanoid robotics systems are evaluated in industrial settings. "
                                "Engineers examine robot balance, safety, and task performance. " * 30),
                },
            ]
            summary, session_id, accepted = pipeline.analyse_and_store(
                "humanoid robots",
                "Research the development of humanoid robots, their real-world "
                "applications, current limitations, and future prospects.",
                pages
            )
            self.assertTrue(summary)
            self.assertEqual(accepted, 2)
            session = pipeline.store.connection.execute(
                "SELECT status, metadata_json FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()
            self.assertEqual(session["status"], "completed")
            self.assertIn('"independent_publishers": 2', session["metadata_json"])
        finally:
            pipeline.close()

    def test_multi_aspect_summary_with_partial_coverage_is_not_saved(self):
        partial = (
            "Overview\nThe topic is covered by two retrieved sources.\n\n"
            "Requested aspects coverage\n"
            "- Development: SUPPORTED [1].\n"
            "- Applications: PARTIAL; deployment evidence is limited [2].\n"
            "- Limitations: SUPPORTED [2].\n"
            "- Future prospects: NOT FOUND in the supplied sources.\n\n"
            "Key findings\n"
            "- The sources describe humanoid robot development [1].\n"
            "- They discuss some engineering constraints [2].\n\n"
            "Evidence limitations\nThe sources do not establish all requested aspects.\n\n"
            "Open questions\nFurther evidence is needed."
        )
        pipeline = ResearchPipeline(FakeLLM(partial), self.db_path)
        try:
            pages = [
                {
                    "url": "https://example.org/one",
                    "title": "Humanoid robot research",
                    "publisher": "Publisher One",
                    "content": ("Humanoid robots are developed for practical tasks. "
                                "Researchers examine humanoid mobility and control. " * 30),
                },
                {
                    "url": "https://example.net/two",
                    "title": "Humanoid robotics limitations",
                    "publisher": "Publisher Two",
                    "content": ("Humanoid robotics systems face engineering constraints. "
                                "Engineers evaluate safety and task performance. " * 30),
                },
            ]
            summary, session_id, accepted = pipeline.analyse_and_store(
                "humanoid robots",
                "Research humanoid robot development, applications, limitations, "
                "and future prospects.",
                pages
            )
            self.assertIsNone(summary)
            self.assertEqual(accepted, 2)
            status = pipeline.store.connection.execute(
                "SELECT status FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()["status"]
            self.assertEqual(status, "partial")
            self.assertIsNone(pipeline.store.get_topic_knowledge("humanoid robots"))
        finally:
            pipeline.close()

    def test_explicit_evidence_gaps_are_not_saved_as_complete_knowledge(self):
        incomplete = (
            "Overview\nA brief overview based on the only retrieved source.\n\n"
            "Key findings\n- The source describes humanoid robot design [1].\n"
            "- It discusses perception and interaction [1].\n\n"
            "Evidence limitations\nThe source does not address real-world deployments "
            "or current engineering limitations, so these aspects remain unsupported.\n\n"
            "Open questions\nWhat evidence establishes deployment outcomes and reliability?"
        )
        pipeline = ResearchPipeline(FakeLLM(incomplete), self.db_path)
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "robotics", "Research robotics",
                [{
                    "url": "https://example.org/robotics",
                    "title": "Robotics research",
                    "publisher": "Example Institute",
                    "content": ("Robotics research examines autonomous systems and "
                                "robotic manipulation in practical environments. " * 30),
                }]
            )
            self.assertIsNone(summary)
            self.assertEqual(accepted, 1)
            status = pipeline.store.connection.execute(
                "SELECT status FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()["status"]
            self.assertEqual(status, "partial")
            self.assertIsNone(pipeline.store.get_topic_knowledge("robotics"))
        finally:
            pipeline.close()

    def test_model_timeout_is_not_saved_as_successful_summary(self):
        llm = FakeLLM("Ollama took too long to respond.")
        pipeline = ResearchPipeline(llm, self.db_path)
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "robotics",
                "Research robotics",
                [{
                    "url": "https://example.org/robotics",
                    "title": "Robotics research",
                    "source": "example.org",
                    "content": ("Robotics research and robotic systems. " * 100),
                }]
            )
            self.assertIsNone(summary)
            self.assertEqual(accepted, 1)
            session = pipeline.store.connection.execute(
                "SELECT status, summary FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()
            self.assertEqual(session["status"], "analysis_failed")
            self.assertEqual(session["summary"], "")
            self.assertIsNone(pipeline.store.get_topic_knowledge("robotics"))
        finally:
            pipeline.close()


if __name__ == "__main__":
    unittest.main()
