import os
import tempfile
import unittest

from core.intent import IntentFastPath
from core.intent_runner import IntentRunner
from core.task_manager import TaskManager
from tools.router import ToolResult


class FakeRouter:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on

    def execute(self, command):
        if command == self.fail_on:
            return ToolResult(False, "The requested action failed.")
        return ToolResult(True, "Completed: " + command)


class TaskExecutionTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.temp.name, "nexus.db")
        self.tasks = TaskManager(self.database)

    def tearDown(self):
        self.tasks.close()
        self.temp.cleanup()

    def make_runner(self, fail_on=None):
        return IntentRunner(
            router=FakeRouter(fail_on=fail_on),
            fast=IntentFastPath(["youtube"], ["notepad", "opera"]),
            planner=None,
            run_builtin=lambda action, value: "Completed built-in action.",
            task_manager=self.tasks
        )

    def test_multi_step_request_is_persisted_as_completed(self):
        runner = self.make_runner()
        result = runner.resolve("open notepad and open opera")
        self.assertTrue(result.success)
        task = self.tasks.list_tasks(1)[0]
        self.assertEqual(task["status"], "completed")
        self.assertEqual(
            [step["status"] for step in task["steps"]],
            ["completed", "completed"]
        )

    def test_failed_step_stops_and_records_remaining_steps_as_skipped(self):
        runner = self.make_runner(fail_on="open notepad")
        result = runner.resolve("open notepad and open opera")
        self.assertFalse(result.success)
        self.assertTrue(result.handled)
        self.assertIn("failed", result.message.lower())
        task = self.tasks.list_tasks(1)[0]
        self.assertEqual(task["status"], "failed")
        self.assertEqual(
            [step["status"] for step in task["steps"]],
            ["failed", "skipped"]
        )

    def test_single_step_request_does_not_create_task_record(self):
        runner = self.make_runner()
        runner.resolve("open notepad")
        self.assertEqual(self.tasks.list_tasks(5), [])


if __name__ == "__main__":
    unittest.main()
