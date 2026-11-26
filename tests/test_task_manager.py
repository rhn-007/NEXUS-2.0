import os
import tempfile
import unittest
from types import SimpleNamespace

from core.task_manager import TaskManager


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "tasks.db")
        self.manager = TaskManager(self.path)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def make_steps(self):
        return [
            SimpleNamespace(action="open_app", value="notepad", command="open notepad"),
            SimpleNamespace(action="research", value="robotics", command="research robotics")
        ]

    def test_task_and_steps_are_created_in_order(self):
        task_id = self.manager.create_task("open notepad then research robotics", self.make_steps())
        task = self.manager.get_task(task_id)
        self.assertEqual(task["status"], "queued")
        self.assertEqual([step["action"] for step in task["steps"]], ["open_app", "research"])
        self.assertEqual([step["status"] for step in task["steps"]], ["pending", "pending"])

    def test_step_progress_and_completion_are_persistent(self):
        task_id = self.manager.create_task("two steps", self.make_steps())
        self.assertTrue(self.manager.start_step(task_id, 0))
        self.assertTrue(self.manager.finish_step(task_id, 0, "completed", "Opened Notepad"))
        self.assertTrue(self.manager.start_step(task_id, 1))
        self.assertTrue(self.manager.finish_step(task_id, 1, "completed", "Research complete"))
        self.assertTrue(self.manager.complete_task(task_id, "Finished both steps"))
        task = self.manager.get_task(task_id)
        self.assertEqual(task["status"], "completed")
        self.assertEqual([step["status"] for step in task["steps"]], ["completed", "completed"])

    def test_failure_skips_later_steps(self):
        task_id = self.manager.create_task("two steps", self.make_steps())
        self.manager.start_step(task_id, 0)
        self.manager.finish_step(task_id, 0, "failed", "Could not open app")
        self.manager.skip_remaining(task_id, 0)
        self.manager.set_task_status(task_id, "failed", "Task stopped after a failed step")
        task = self.manager.get_task(task_id)
        self.assertEqual(task["status"], "failed")
        self.assertEqual([step["status"] for step in task["steps"]], ["failed", "skipped"])

    def test_task_history_survives_reopening_database(self):
        task_id = self.manager.create_task("two steps", self.make_steps())
        self.manager.close()
        self.manager = TaskManager(self.path)
        self.assertIsNotNone(self.manager.get_task(task_id))

    def test_meeting_codes_are_redacted(self):
        task_id = self.manager.create_task(
            "join abc-defg-hij",
            [SimpleNamespace(action="join_meeting", value="abc-defg-hij",
                              command="join meeting abc-defg-hij")]
        )
        task = self.manager.get_task(task_id)
        self.assertNotIn("abc-defg-hij", str(task))
        self.assertIn("[meeting code]", str(task))


if __name__ == "__main__":
    unittest.main()
