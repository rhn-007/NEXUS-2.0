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
    wants_meeting,
    wants_new_meeting
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


def plan_for(step, text="get me into my meeting"):
    planner = IntentPlanner("u", "m", ["youtube"], ["notepad"])
    data = {"decision": "act", "steps": [step], "question": ""}
    with patch("core.planner.requests.post", return_value=answer(data)):
        return planner.plan(text)


class PlannerMeeting(unittest.TestCase):
    def test_valid_code(self):
        plan = plan_for({"action": "join_meeting", "value": "abc defg hij"})
        self.assertEqual([s.command for s in plan.steps], [f"join meeting {CODE}"])

    def test_missing_code_asks_and_waits_for_it(self):
        plan = plan_for({"action": "join_meeting", "value": ""})
        self.assertEqual(plan.kind, "ask")
        self.assertEqual(plan.expects, "meet_code")

    def test_meeting_action_is_ignored_for_unrelated_requests(self):
        # Seen on the real machine: "play the current song on spotify"
        # made the model pick join_meeting and NEXUS asked for a code.
        for text in ["play the current song on spotify", "call my mom"]:
            plan = plan_for({"action": "join_meeting", "value": ""}, text)
            self.assertEqual(plan.kind, "chat", text)
            self.assertEqual(plan.question, "", text)

    def test_code_in_the_message_still_counts(self):
        plan = plan_for(
            {"action": "join_meeting", "value": "abc defg hij"},
            "hop on abc-defg-hij"
        )
        self.assertEqual([s.command for s in plan.steps], [f"join meeting {CODE}"])

    def test_junk_value_never_becomes_a_command(self):
        plan = plan_for({"action": "join_meeting", "value": "x; del /s *"})
        self.assertEqual(plan.kind, "ask")


class StartNewMeeting(unittest.TestCase):
    def tool(self):
        browser = MagicMock()
        browser.open_opera.return_value = ToolResponse.success("Opening the website in Opera.")
        return MeetTool(browser), browser

    def test_these_start_a_new_meeting(self):
        for text in ["start a new meeting", "can you start a meeting",
                     "create a google meet", "make me a new google meet",
                     "host a video call", "open a new meeting", "new meeting",
                     "start an instant meeting", "set up a meeting",
                     "get me a new google meet"]:
            self.assertTrue(wants_new_meeting(text), text)

    def test_these_do_not(self):
        for text in ["join the meeting abc-defg-hij", "start meeting abc-defg-hij",
                     "how do i start a meeting", "make a call to mom",
                     "open the meeting", "what is a google meet",
                     "schedule a meeting for 5pm", "i have a meeting at 5",
                     "start the music", "get a meeting"]:
            self.assertFalse(wants_new_meeting(text), text)

    def test_it_opens_only_the_new_meeting_link(self):
        tool, browser = self.tool()
        self.assertTrue(tool.can_handle("start meeting"))
        result = tool.execute("start meeting; open notepad && del *")
        browser.open_opera.assert_called_once_with("https://meet.google.com/new")
        self.assertTrue(result.success)
        self.assertIn("signed in", result.message)
        self.assertIn("address bar", result.message)

    def test_joining_with_a_code_still_joins(self):
        tool, browser = self.tool()
        # A code always means "open that meeting", whatever the verb.
        tool.execute(f"start meeting {CODE}")
        browser.open_opera.assert_called_once_with(f"https://meet.google.com/{CODE}")

    def test_browser_problems_are_passed_on(self):
        tool, browser = self.tool()
        browser.open_opera.return_value = ToolResponse.failure("I couldn't find Opera on your computer.")
        self.assertIn("Opera", tool.execute("start meeting").message)
        self.assertFalse(MeetTool(None).execute("start meeting").success)

    def test_fast_path_runs_it_before_the_router(self):
        steps = fast().fast_steps("ok can you start a new google meet")
        self.assertEqual([(s.action, s.command, s.first) for s in steps],
                         [("start_meeting", "start meeting", True)])

    def test_a_code_goes_to_join_not_start(self):
        steps = fast().fast_steps(f"join the meeting {CODE}")
        self.assertEqual(steps[0].action, "join_meeting")


class PlannerStartMeeting(unittest.TestCase):
    def test_valid(self):
        plan = plan_for({"action": "start_meeting", "value": ""},
                        "let's set up a video call")
        self.assertEqual([s.command for s in plan.steps], ["start meeting"])

    def test_ignored_without_a_meeting_in_the_message(self):
        plan = plan_for({"action": "start_meeting", "value": ""}, "start the music")
        self.assertEqual(plan.kind, "chat")

    def test_ignored_when_the_message_does_not_ask_to_start(self):
        plan = plan_for({"action": "start_meeting", "value": ""},
                        "what time is my meeting")
        self.assertEqual(plan.kind, "chat")


class StartMeetingEndToEnd(unittest.TestCase):
    def test_through_the_real_router_and_runner(self):
        from tools.registry import ToolRegistry
        from tools.router import ToolRouter

        browser = MagicMock()
        browser.name = "browser"
        browser.can_handle.return_value = False
        browser.open_opera.return_value = ToolResponse.success("Opening the website in Opera.")
        registry = ToolRegistry()
        registry.register(browser)
        registry.register(MeetTool(browser))
        runner = IntentRunner(ToolRouter(registry), fast(), MagicMock(), MagicMock())
        result = runner.resolve("can u start a new meeting")
        self.assertTrue(result.success)
        self.assertIn("new Google Meet", result.message)
        browser.open_opera.assert_called_once_with("https://meet.google.com/new")


if __name__ == "__main__":
    unittest.main()
