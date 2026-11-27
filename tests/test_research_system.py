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
        self.responses = list(response) if isinstance(response, list) else [response]
        self.response_index = 0
        self.last_prompt = None
        self.prompts = []

    def generate_response(self, message, context=None):
        self.last_prompt = message
        self.prompts.append(message)
        response = self.responses[min(self.response_index, len(self.responses) - 1)]
        self.response_index += 1
        return response


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
            self.assertIn('"topic_knowledge_saved": true', session["metadata_json"])
        finally:
            pipeline.close()

    def test_pipeline_uses_one_synthesis_call_and_stores_brief(self):
        pipeline = ResearchPipeline(FakeLLM(), self.db_path)
        try:
            query = (
                "Research autonomous vehicles, their applications in transportation "
                "and logistics, enabling technologies, safety challenges, and future impact."
            )
            summary, session_id, accepted = pipeline.analyse_and_store(
                "autonomous vehicles",
                query,
                [{
                    "url": "https://example.org/autonomous-vehicles",
                    "title": "Autonomous vehicle research",
                    "publisher": "Example Institute",
                    "content": (
                        "Autonomous vehicles use sensors and software to navigate. "
                        "Researchers evaluate perception, planning, and control systems. "
                        "Applications include transportation and logistics. "
                    ) * 30,
                }]
            )
            self.assertTrue(summary)
            self.assertEqual(accepted, 1)
            self.assertEqual(len(pipeline.llm.prompts), 1)
            self.assertIn("Address every distinct aspect", pipeline.llm.prompts[0])
            self.assertIn("Sources list containing the exact URLs", pipeline.llm.prompts[0])
            session = pipeline.store.connection.execute(
                "SELECT status, metadata_json, summary FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()
            self.assertEqual(session["status"], "completed")
            self.assertEqual(session["summary"], summary)
            self.assertIn('"synthesis_calls": 1', session["metadata_json"])
            topic = pipeline.store.get_topic_knowledge("autonomous vehicles")
            self.assertIsNotNone(topic)
            self.assertEqual(topic["summary"], summary)
        finally:
            pipeline.close()


    def test_brief_with_evidence_gaps_is_stored_with_caveats(self):
        partial = (
            "Overview\nThe sources cover development but provide limited deployment data.\n\n"
            "Key findings\n- Researchers are developing autonomous vehicle systems [SOURCE 1].\n"
            "- The source discusses perception and control but not broad fleet outcomes [SOURCE 1].\n\n"
            "Evidence limitations\nThe supplied evidence does not establish long-term safety "
            "or effects on employment.\n\n"
            "Open questions\nHow do large-scale deployments affect safety and work?"
        )
        pipeline = ResearchPipeline(FakeLLM(partial), self.db_path)
        try:
            summary, session_id, accepted = pipeline.analyse_and_store(
                "autonomous vehicles",
                "Research autonomous vehicle development, applications, limitations, and future impacts.",
                [{
                    "url": "https://example.org/vehicles",
                    "title": "Autonomous vehicle development",
                    "publisher": "Example Institute",
                    "content": (
                        "Autonomous vehicles use sensors and control software. "
                        "Researchers study vehicle perception and navigation. "
                    ) * 30,
                }]
            )
            self.assertEqual(summary, partial)
            self.assertEqual(accepted, 1)
            session = pipeline.store.connection.execute(
                "SELECT status FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()
            self.assertEqual(session["status"], "completed")
            self.assertEqual(
                pipeline.store.get_topic_knowledge("autonomous vehicles")["summary"],
                partial
            )
        finally:
            pipeline.close()


    def test_explicit_evidence_gaps_are_preserved_in_stored_brief(self):
        incomplete = (
            "Overview\nA brief overview based on the retrieved source.\n\n"
            "Key findings\n- The source describes robotics design [SOURCE 1].\n"
            "- It discusses perception and interaction [SOURCE 1].\n\n"
            "Evidence limitations\nThe source does not address real-world deployments "
            "or current engineering limitations.\n\n"
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
                    "content": (
                        "Robotics research examines autonomous systems and "
                        "robotic manipulation in practical environments. "
                    ) * 30,
                }]
            )
            self.assertEqual(summary, incomplete)
            self.assertEqual(accepted, 1)
            status = pipeline.store.connection.execute(
                "SELECT status FROM research_sessions WHERE id=?",
                (session_id,)
            ).fetchone()["status"]
            self.assertEqual(status, "completed")
            self.assertIsNotNone(pipeline.store.get_topic_knowledge("robotics"))
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
