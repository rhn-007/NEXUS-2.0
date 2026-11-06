import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from learning.daily_worker import DailyLearningWorker


class DailyLearningWorkerTests(unittest.TestCase):
    def setUp(self):
        self.knowledge = MagicMock()
        self.knowledge.get_all_knowledge.return_value = [
            {
                "topic": "Humanoid robots",
                "learned_at": "2026-11-01T10:00:00",
                "title": "Introduction",
                "content": "Stored information"
            }
        ]
        self.knowledge.get_learning_history.return_value = []
        self.store = MagicMock()
        self.store.get_topic_knowledge.return_value = {
            "summary": "Existing overview",
            "open_questions": []
        }
        self.llm = MagicMock()
        self.llm.generate_response.return_value = (
            '{"topic": "Humanoid robots", '
            '"research_question": "What are the main technical challenges?"}'
        )
        self.research = MagicMock()
        self.research.research_topic.return_value = SimpleNamespace(
            success=True,
            message="Research completed."
        )
        self.worker = DailyLearningWorker(
            knowledge=self.knowledge,
            llm=self.llm,
            research_tool=self.research,
            research_store=self.store
        )

    def test_daily_session_plans_and_runs_research(self):
        result = self.worker.run()
        self.assertEqual(result, 0)
        self.research.research_topic.assert_called_once_with(
            "Humanoid robots",
            research_question="What are the main technical challenges?"
        )
        activities = [
            call.kwargs.get("activity")
            for call in self.knowledge.record_activity.call_args_list
        ]
        self.assertIn("daily_autonomous_learning_completed", activities)

    def test_no_existing_knowledge_skips_without_research(self):
        self.knowledge.get_all_knowledge.return_value = []
        result = self.worker.run()
        self.assertEqual(result, 0)
        self.research.research_topic.assert_not_called()

    def test_completed_session_today_is_not_repeated(self):
        today = self.worker._today()
        self.knowledge.get_learning_history.return_value = [{
            "activity": "daily_autonomous_learning_completed",
            "created_at": today + "T17:10:00"
        }]
        result = self.worker.run()
        self.assertEqual(result, 0)
        self.research.research_topic.assert_not_called()

    def test_planner_cannot_select_unknown_topic(self):
        self.llm.generate_response.return_value = (
            '{"topic": "Unrelated topic", '
            '"research_question": "What should be investigated?"}'
        )
        with self.assertRaises(ValueError):
            self.worker._plan_research([{"topic": "Humanoid robots"}])


if __name__ == "__main__":
    unittest.main()
