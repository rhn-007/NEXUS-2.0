import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.action_history import ActionHistory
from core.intent import IntentFastPath
from core.intent_runner import IntentRunner
from tools.router import ToolResult


class WithHistory(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "h.db")
        self.history = ActionHistory(self.path)

    def tearDown(self):
        self.history.close()
        self.dir.cleanup()


class Recording(WithHistory):
    def test_an_action_is_kept_with_everything_about_it(self):
        self.history.record("open notepad", "open_app", "open notepad", True, "Opening Notepad.")
        item = self.history.recent(1)[0]
        self.assertEqual((item["request"], item["action"], item["command"],
                          item["success"], item["message"]),
                         ("open notepad", "open_app", "open notepad", 1, "Opening Notepad."))
        self.assertRegex(item["created_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_newest_first(self):
        for name in ["one", "two", "three"]:
            self.history.record(name, "x", name, True, "")
        self.assertEqual([i["request"] for i in self.history.recent(5)], ["three", "two", "one"])

    def test_it_survives_a_restart(self):
        self.history.record("open notepad", "open_app", "open notepad", True, "ok")
        self.history.close()
        self.history = ActionHistory(self.path)
        self.assertEqual(self.history.recent(1)[0]["request"], "open notepad")

    def test_only_the_newest_are_kept(self):
        small = ActionHistory(os.path.join(self.dir.name, "s.db"), keep=5)
        for i in range(20):
            small.record(f"r{i}", "x", "c", True, "")
        kept = small.recent(50)
        self.assertEqual(len(kept), 5)
        self.assertEqual(kept[0]["request"], "r19")
        small.close()

    def test_long_text_is_cut(self):
        self.history.record("x" * 5000, "a", "y" * 5000, True, "z" * 5000)
        item = self.history.recent(1)[0]
        self.assertLessEqual(len(item["request"]), 200)
        self.assertLessEqual(len(item["message"]), 300)

    def test_a_meeting_code_is_never_stored(self):
        self.history.record("join the meeting abc-defg-hij", "join_meeting",
                            "join meeting abc-defg-hij", True, "Joining abc-defg-hij.")
        self.history.record("open this abc-defg-hij please", "open_website",
                            "open abc-defg-hij", True, "Opening abc-defg-hij")
        everything = str(self.history.recent(5))
        self.assertNotIn("abc-defg-hij", everything)
        self.assertIn("join a Google Meet", everything)

    def test_a_broken_database_never_breaks_a_command(self):
        self.history.connection.close()
        self.history.record("open notepad", "open_app", "open notepad", True, "ok")


class Answers(WithHistory):
    def test_did_that_work_uses_the_last_action(self):
        self.history.record("open notepad", "open_app", "open notepad", True, "Opening Notepad.")
        for text in ["did that work", "Did it work?", "did that go through", "was that successful",
                     "what did you just do"]:
            reply = self.history.answer(text)
            self.assertIn("open notepad", reply, text)
            self.assertIn("success", reply, text)
            self.assertIn("can't see your screen", reply, text)

    def test_a_failure_is_reported_as_a_failure(self):
        self.history.record("open foo", "open_app", "open foo", False, "I couldn't find foo.")
        reply = self.history.answer("did that work")
        self.assertIn("it failed", reply)
        self.assertIn("I couldn't find foo.", reply)

    def test_what_have_you_opened_lists_the_recent_ones(self):
        for name in ["open notepad", "open documents", "open opera", "open calculator"]:
            self.history.record(name, "open_app", name, True, "ok")
        reply = self.history.answer("what have you opened")
        for name in ["open notepad", "open documents", "open opera", "open calculator"]:
            self.assertIn(name, reply)
        self.assertLess(reply.index("open calculator"), reply.index("open notepad"))
        self.assertIsNotNone(self.history.answer("did those work"))
        self.assertIsNotNone(self.history.answer("show action history"))

    def test_nothing_done_yet(self):
        self.assertEqual(self.history.answer("what have you done"),
                         "I haven't done anything on your computer yet.")
        # a plain "did that work" with nothing to report is just conversation
        self.assertIsNone(self.history.answer("did that work"))

    def test_other_sentences_are_left_alone(self):
        self.history.record("open notepad", "open_app", "open notepad", True, "ok")
        for text in ["open notepad", "explain how it works", "what is the date",
                     "did the team win", "", None, "x" * 500]:
            self.assertIsNone(self.history.answer(text), text)


class WithRunner(WithHistory):
    def runner(self, executed):
        router = MagicMock()
        router.execute.side_effect = executed
        runner = IntentRunner(router, IntentFastPath(["youtube"], ["notepad", "opera"]),
                              MagicMock(), MagicMock(), history=self.history)
        return runner, router


class RunnerRecords(WithRunner):
    def test_a_fast_step_is_recorded_with_the_request_and_result(self):
        runner, _ = self.runner(lambda cmd: ToolResult(True, "Opening Notepad."))
        runner.resolve("can you open notepad for me")
        item = self.history.recent(1)[0]
        self.assertEqual(item["request"], "can you open notepad for me")
        self.assertEqual(item["success"], 1)
        self.assertEqual(item["message"], "Opening Notepad.")

    def test_a_multi_step_request_records_each_step(self):
        runner, _ = self.runner(lambda cmd: ToolResult(True, f"done {cmd}"))
        runner.resolve("open notepad and open opera")
        self.assertEqual(len(self.history.recent(5)), 2)

    def test_a_failed_step_is_recorded_as_failed(self):
        runner, _ = self.runner(lambda cmd: ToolResult(False, "Couldn't find it."))
        runner.resolve("open notepad and open opera")
        item = self.history.recent(5)[0]
        self.assertEqual(item["success"], 0)

    def test_the_router_path_is_recorded_too(self):
        runner, router = self.runner(lambda cmd: ToolResult(True, "2 + 2 = 4"))
        runner.resolve("calculate 2 + 2")
        self.assertEqual(self.history.recent(1)[0]["action"], "command")

    def test_asking_about_history_is_not_itself_an_action(self):
        runner, router = self.runner(lambda cmd: ToolResult(True, "Opening Notepad."))
        runner.resolve("open notepad")
        router.execute.reset_mock()
        reply = runner.resolve("did that work")
        self.assertTrue(reply.success)
        self.assertIn("open notepad", reply.message)
        router.execute.assert_not_called()
        self.assertEqual(len(self.history.recent(10)), 1)

    def test_chat_is_not_recorded(self):
        runner, _ = self.runner(lambda cmd: ToolResult(False, ""))
        runner.planner.plan.return_value = MagicMock(kind="chat", valid=True, steps=[],
                                                     question="", planner_ms=1, expects=None)
        runner.resolve("tell me a joke")
        self.assertEqual(self.history.recent(5), [])

    def test_a_meeting_code_never_reaches_the_history(self):
        runner, _ = self.runner(lambda cmd: ToolResult(True, "Joining the meeting."))
        runner.resolve("join the meeting abc-defg-hij")
        self.assertNotIn("abc-defg-hij", str(self.history.recent(5)))

    def test_it_all_works_without_a_history(self):
        router = MagicMock()
        router.execute.return_value = ToolResult(True, "Opening Notepad.")
        runner = IntentRunner(router, IntentFastPath([], ["notepad"]), MagicMock(), MagicMock())
        self.assertTrue(runner.resolve("open notepad").success)


if __name__ == "__main__":
    unittest.main()
