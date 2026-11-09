import json
import unittest
from unittest.mock import MagicMock, patch

from core.intent import IntentFastPath
from core.intent_runner import IntentRunner
from core.planner import IntentPlanner
from tools.meet import (
    MeetTool,
    looks_like_code_attempt,
    parse_meet_code,
    wants_meeting
)
from tools.response import ToolResponse
from tools.router import ToolResult

CODE = "abc-defg-hij"


class ParseCodes(unittest.TestCase):
    def test_typed_and_spoken_forms(self):
        for text in [
            "join meeting abc-defg-hij",
            "Join meeting ABC-DEFG-HIJ",
            "can you get me into the meet, the code is abc defg hij",
            "join meeting abcdefghij please",
            "join meeting a b c d e f g h i j",
            "join the call a, b, c, d, e, f, g, h, i, j",
            "join meeting abc dash defg dash hij",
            "join the call alpha bravo charlie delta echo foxtrot golf hotel india juliet",
            "the code is abc defg hij",
            "abc defg hij",
            "join meeting https://meet.google.com/abc-defg-hij",
        ]:
            self.assertEqual(parse_meet_code(text), CODE, text)

    def test_letter_names_are_a_last_resort(self):
        # Letter names are only used when the plain reading is not 10 letters.
        self.assertEqual(
            parse_meet_code("join meeting a bee see dee echo foxtrot gee hotel india jay"),
            CODE
        )

    def test_not_ten_letters_means_no_code(self):
        for text in [
            "join my meeting",
            "join meeting abc-defg",
            "join meeting abc defg hijk",
            "can join the meeting",
            "join meeting",
        ]:
            self.assertIsNone(parse_meet_code(text), text)

    def test_wants_meeting(self):
        self.assertTrue(wants_meeting("can you get me into the meeting"))
        self.assertTrue(wants_meeting("join google meet"))
        self.assertFalse(wants_meeting("open notepad"))
        self.assertFalse(wants_meeting("I will meet him tomorrow"))
        self.assertFalse(wants_meeting("what is a conference call"))

    def test_garbled_code_detection(self):
        self.assertTrue(looks_like_code_attempt("a b c d e f g h i"))
        self.assertTrue(looks_like_code_attempt("abc defgh hi"))
        self.assertFalse(looks_like_code_attempt("open notepad"))
        self.assertFalse(looks_like_code_attempt("what is the weather today"))


class MeetToolOpensOnlyMeet(unittest.TestCase):
    def tool(self):
        browser = MagicMock()
        browser.open_opera.return_value = ToolResponse.success("Opening the website in Opera.")
        return MeetTool(browser), browser

    def test_opens_the_meet_link_for_the_code(self):
        tool, browser = self.tool()
        self.assertTrue(tool.can_handle("could you join meeting abc defg hij"))
        result = tool.execute("could you join meeting abc defg hij")
        browser.open_opera.assert_called_once_with(f"https://meet.google.com/{CODE}")
        self.assertTrue(result.success)
        self.assertIn(CODE, result.message)

    def test_extra_text_never_reaches_the_url(self):
        tool, browser = self.tool()
        tool.execute("join meeting abc-defg-hij; open notepad && del *")
        browser.open_opera.assert_called_once_with(f"https://meet.google.com/{CODE}")

    def test_other_hosts_in_the_text_are_ignored(self):
        tool, browser = self.tool()
        tool.execute("join meeting https://evil.example/abc-defg-hij")
        url = browser.open_opera.call_args.args[0]
        self.assertTrue(url.startswith("https://meet.google.com/"))

    def test_without_a_code_it_asks(self):
        tool, browser = self.tool()
        self.assertFalse(tool.can_handle("join my meeting"))
        self.assertFalse(tool.execute("join my meeting").success)
        browser.open_opera.assert_not_called()

    def test_code_is_not_logged(self):
        tool, _ = self.tool()
        with self.assertLogs("tools.meet", level="INFO") as logs:
            tool.execute(f"join meeting {CODE}")
        self.assertNotIn(CODE, "\n".join(logs.output))

    def test_browser_failure_is_passed_on(self):
        tool, browser = self.tool()
        browser.open_opera.return_value = ToolResponse.failure("I couldn't find Opera on your computer.")
        self.assertIn("Opera", tool.execute(f"join meeting {CODE}").message)


def fast():
    return IntentFastPath(["youtube"], ["notepad"])


class FastPathAndFollowUp(unittest.TestCase):
    def make(self, router_results=()):
        router = MagicMock()
        router.execute.side_effect = list(router_results)
        runner = IntentRunner(router, fast(), MagicMock(), MagicMock(), MagicMock())
        return runner, router

    def test_natural_sentence_with_code_joins_without_asking(self):
        runner, router = self.make([ToolResult(True, "Opening Meet.")])
        result = runner.resolve("hey can you get me into the meeting, code is abc defg hij")
        router.execute.assert_called_once_with(f"join meeting {CODE}")
        self.assertEqual(result.message, "Opening Meet.")

    def test_missing_code_is_asked_for_then_used(self):
        runner, router = self.make([ToolResult(True, "Opening Meet.")])
        asked = runner.resolve("can you join my meeting")
        self.assertEqual(asked.message, "What's the meeting code?")
        self.assertIsNotNone(runner.pending)
        router.execute.assert_not_called()

        answered = runner.resolve("abc defg hij")
        router.execute.assert_called_once_with(f"join meeting {CODE}")
        self.assertTrue(answered.success)
        self.assertIsNone(runner.pending)

    def test_garbled_code_is_asked_again_then_gives_up(self):
        runner, router = self.make([ToolResult(), ToolResult(), ToolResult()])
        runner.resolve("join my meeting")
        first = runner.resolve("a b c d e f g h i")
        self.assertIn("didn't catch", first.message)
        second = runner.resolve("a b c d e f g h i")
        self.assertIn("didn't catch", second.message)
        third = runner.resolve("a b c d e f g h i")
        self.assertIsNone(runner.pending)
        self.assertNotIn("didn't catch", third.message)

    def test_cancel_clears_the_question(self):
        runner, _ = self.make()
        runner.resolve("join my meeting")
        self.assertEqual(runner.resolve("never mind").message, "Okay, cancelled.")
        self.assertIsNone(runner.pending)

    def test_unrelated_request_is_handled_normally(self):
        runner, router = self.make([ToolResult(True, "Opening Notepad.")])
        runner.resolve("join my meeting")
        result = runner.resolve("open notepad")
        self.assertEqual(result.message, "Opening Notepad.")
        self.assertIsNone(runner.pending)

    def test_meeting_then_another_task(self):
        runner, router = self.make([ToolResult(True, "Opening Meet."), ToolResult(True, "Opening Notepad.")])
        result = runner.resolve(f"join meeting {CODE} and then open notepad")
        self.assertEqual(result.message, "Opening Meet.\nOpening Notepad.")

    def test_observation_never_contains_the_code(self):
        runner, _ = self.make([ToolResult(True, "ok")])
        runner.resolve(f"join meeting {CODE}")
        event = runner.observer.record_event.call_args.kwargs
        self.assertNotIn("abc", json.dumps(event["metadata"]))


def answer(data):
    response = MagicMock()
    response.ok = True
    response.json.return_value = {"message": {"content": json.dumps(data)}}
    return response


def plan_for(step):
    planner = IntentPlanner("u", "m", ["youtube"], ["notepad"])
    data = {"decision": "act", "steps": [step], "question": ""}
    with patch("core.planner.requests.post", return_value=answer(data)):
        return planner.plan("x")


class PlannerMeeting(unittest.TestCase):
    def test_valid_code(self):
        plan = plan_for({"action": "join_meeting", "value": "abc defg hij"})
        self.assertEqual([s.command for s in plan.steps], [f"join meeting {CODE}"])

    def test_missing_code_asks_and_waits_for_it(self):
        plan = plan_for({"action": "join_meeting", "value": ""})
        self.assertEqual(plan.kind, "ask")
        self.assertEqual(plan.expects, "meet_code")

    def test_junk_value_never_becomes_a_command(self):
        plan = plan_for({"action": "join_meeting", "value": "x; del /s *"})
        self.assertEqual(plan.kind, "ask")


if __name__ == "__main__":
    unittest.main()
