import json
import unittest
from unittest.mock import MagicMock, patch

from core.intent import IntentFastPath, Step, app_targets_from
from core.intent_runner import IntentRunner
from core.planner import IntentPlanner, MAX_STEPS
from tools.router import ToolResult

WEBSITES = ["youtube", "github", "whatsapp web", "google"]
APPS = ["notepad", "calculator", "spotify", "downloads", "file explorer"]


def fast():
    return IntentFastPath(WEBSITES, APPS)


def commands(text):
    return [step.command for step in fast().fast_steps(text)]


class FastPathUnderstandsRequests(unittest.TestCase):
    def test_messages_from_the_real_log(self):
        self.assertEqual(commands("can u reseach about openai"), ["research openai"])
        self.assertEqual(
            commands("now research about claud and its difference from openai"),
            ["research claud and its difference from openai"]
        )
        self.assertEqual(
            commands("ok. can you open browser and search for sam altman"),
            ["search sam altman"]
        )
        self.assertEqual(commands("open browser"), ["open browser"])
        self.assertEqual(commands("ok, now can u research about xyz"), ["research xyz"])

    def test_polite_and_indirect_wording(self):
        self.assertEqual(commands("could you please open notepad"), ["open notepad"])
        self.assertEqual(commands("I want you to research black holes"), ["research black holes"])
        self.assertEqual(commands("nexus, pull up spotify for me"), ["open spotify"])
        self.assertEqual(commands("Hey, can you look up the weather in Kuwait?"), ["search the weather in kuwait"])
        self.assertEqual(commands("launch youtube"), ["go to youtube"])
        self.assertEqual(commands("serch for cats on google"), ["search cats"])
        self.assertEqual(commands("go to github"), ["go to github"])

    def test_several_steps(self):
        self.assertEqual(commands("open notepad and calculator"), ["open notepad", "open calculator"])
        self.assertEqual(
            commands("open youtube and then open notepad"),
            ["go to youtube", "open notepad"]
        )

    def test_one_topic_with_and_is_not_split(self):
        self.assertEqual(
            commands("research the history of rome, greece and egypt"),
            ["research the history of rome, greece and egypt"]
        )
        self.assertEqual(
            commands("search for pizza and pasta recipes"),
            ["search pizza and pasta recipes"]
        )

    def test_and_inside_a_search_topic_is_not_a_new_step(self):
        # The exact message that failed on the real machine.
        self.assertEqual(
            commands("can u open browser and search for matrices and determinants"),
            ["search matrices and determinants"]
        )
        self.assertEqual(
            commands("open youtube and search for tom and jerry"),
            ["go to https://www.youtube.com/results?search_query=tom+and+jerry"]
        )
        self.assertEqual(
            commands("research apple and microsoft and then search for apple stock"),
            ["research apple and microsoft", "search apple stock"]
        )

    def test_searching_a_named_site_searches_that_site(self):
        youtube = "go to https://www.youtube.com/results?search_query=the+weeknd"
        # Both messages that went wrong on the real machine.
        self.assertEqual(commands("open youtube and search for the weeknd"), [youtube])
        self.assertEqual(commands("can u open youtube an dsearch for the weeknd"), [youtube])
        self.assertEqual(commands("search youtube for the weeknd"), [youtube])
        self.assertEqual(commands("look up the weeknd on youtube"), [youtube])
        self.assertEqual(
            commands("search github for flask"),
            ["go to https://github.com/search?q=flask"]
        )
        # Plain searches still go to Google.
        self.assertEqual(commands("search for the weeknd"), ["search the weeknd"])

    def test_spoken_arithmetic(self):
        self.assertEqual(commands("what's 12 times 7"), ["calculate 12 * 7"])
        self.assertEqual(commands("whats 15 percent of 80"), ["calculate (15/100*80)"])


class FastPathLeavesChatAlone(unittest.TestCase):
    def test_questions_and_capability_talk_are_not_commands(self):
        for text in [
            "can you search the web?",
            "what is research?",
            "do you research things",
            "i searched for it yesterday",
            "tell me about openai",
            "how are you doing today",
            "what is the current time?",
            "research it",
            "open the pod bay doors",
            "lunch with sam",
            "bye",
            "goodbye",
            "open",
            "search",
        ]:
            self.assertEqual(commands(text), [], text)


class BuiltInFeatures(unittest.TestCase):
    def test_natural_wording_maps_to_existing_commands(self):
        f = fast()
        self.assertEqual(f.builtin_command("can you show me my performance report"), "show performance report")
        self.assertEqual(f.builtin_command("what have you learned about how i speak"), "show my speech profile")
        self.assertEqual(f.builtin_command("forget my speech profile please"), "forget my speech profile")
        self.assertEqual(f.builtin_command("tell me what you know about me"), "what do you know about me")
        self.assertEqual(f.builtin_command("who am i?"), "what do you know about me")
        self.assertIsNone(f.builtin_command("tell me about openai"))

    def test_exit_needs_an_explicit_request(self):
        f = fast()
        self.assertTrue(f.is_exit_request("ok please shut down nexus"))
        self.assertTrue(f.is_exit_request("exit nexus"))
        # Whisper often invents "Bye." from silence, so these must not quit.
        self.assertFalse(f.is_exit_request("bye"))
        self.assertFalse(f.is_exit_request("goodbye"))
        self.assertFalse(f.is_exit_request("I want to exit the building"))

    def test_app_targets_collects_apps_folders_and_explorer(self):
        tool = MagicMock()
        tool.applications = {"n": {"aliases": ["notepad"]}}
        tool.folders = {"downloads": "x"}
        self.assertEqual(
            app_targets_from(tool),
            ["downloads", "explorer", "file explorer", "notepad"]
        )


class RequestGate(unittest.TestCase):
    def test_gate_decides_which_messages_reach_the_planner(self):
        f = fast()
        self.assertTrue(f.looks_like_request("can you pop open my music app"))
        self.assertTrue(f.looks_like_request("please look at youtube for me"))
        self.assertTrue(f.looks_like_request("open foo"))
        self.assertFalse(f.looks_like_request("how are you doing today"))
        self.assertFalse(f.looks_like_request("can you explain black holes"))
        self.assertFalse(f.looks_like_request("what is the capital of france"))
        self.assertFalse(f.looks_like_request("x" * 400))


def planner():
    return IntentPlanner(
        "http://localhost:11434/api/chat",
        "qwen2.5:3b",
        websites=WEBSITES,
        app_names=APPS,
        app_checker=lambda name: name.lower() in APPS
    )


def answer(data):
    response = MagicMock()
    response.ok = True
    response.json.return_value = {"message": {"content": json.dumps(data)}}
    return response


def plan_for(data, text="x", recent=None):
    with patch("core.planner.requests.post", return_value=answer(data)):
        return planner().plan(text, recent)


class PlannerChecksTheModel(unittest.TestCase):
    def test_valid_steps_become_known_commands(self):
        plan = plan_for({
            "decision": "act",
            "steps": [
                {"action": "open_app", "value": "spotify"},
                {"action": "research", "value": "jazz history"}
            ],
            "question": ""
        })
        self.assertEqual(plan.kind, "act")
        self.assertEqual(
            [s.command for s in plan.steps],
            ["open spotify", "research jazz history"]
        )

    def test_chat_decision_means_normal_conversation(self):
        self.assertEqual(plan_for({"decision": "chat", "steps": [], "question": ""}).kind, "chat")

    def test_unknown_action_is_rejected(self):
        plan = plan_for({
            "decision": "act",
            "steps": [{"action": "run_shell", "value": "del /s *"}],
            "question": ""
        })
        self.assertEqual(plan.kind, "chat")
        self.assertFalse(plan.valid)

    def test_unknown_app_turns_into_a_question(self):
        plan = plan_for({
            "decision": "act",
            "steps": [{"action": "open_app", "value": "photoshop"}],
            "question": ""
        })
        self.assertEqual(plan.kind, "ask")
        self.assertIn("photoshop", plan.question)

    def test_bad_values_are_rejected(self):
        for step in [
            {"action": "open_website", "value": "javascript:alert(1)"},
            {"action": "calculate", "value": "__import__('os')"},
            {"action": "research", "value": "x" * 151},
            {"action": "switch_mode", "value": "turbo"},
        ]:
            plan = plan_for({"decision": "act", "steps": [step], "question": ""})
            self.assertEqual(plan.kind, "chat", step)

    def test_websites_and_urls(self):
        plan = plan_for({
            "decision": "act",
            "steps": [
                {"action": "open_website", "value": "YouTube"},
                {"action": "open_website", "value": "https://example.com/a"},
                {"action": "open_website", "value": "example.org"}
            ],
            "question": ""
        })
        self.assertEqual(
            [s.command for s in plan.steps],
            ["go to youtube", "go to https://example.com/a", "go to https://example.org"]
        )

    def test_browser_step_before_a_search_is_dropped(self):
        plan = plan_for({
            "decision": "act",
            "steps": [
                {"action": "open_browser", "value": ""},
                {"action": "web_search", "value": "cats"}
            ],
            "question": ""
        })
        self.assertEqual([s.command for s in plan.steps], ["search cats"])

    def test_at_most_three_steps(self):
        step = {"action": "open_app", "value": "notepad"}
        plan = plan_for({"decision": "act", "steps": [step] * 6, "question": ""})
        self.assertEqual(len(plan.steps), MAX_STEPS)

    def test_clarifying_question(self):
        plan = plan_for({"decision": "ask", "steps": [], "question": "Which folder?"})
        self.assertEqual((plan.kind, plan.question), ("ask", "Which folder?"))

    def test_garbage_and_failures_mean_chat(self):
        bad = MagicMock()
        bad.ok = True
        bad.json.return_value = {"message": {"content": "not json"}}
        with patch("core.planner.requests.post", return_value=bad):
            self.assertEqual(planner().plan("x").kind, "chat")
        with patch("core.planner.requests.post", side_effect=OSError("down")):
            self.assertEqual(planner().plan("x").kind, "chat")

    def test_older_ollama_falls_back_to_plain_json_format(self):
        failed = MagicMock()
        failed.ok = False
        good = answer({"decision": "chat", "steps": [], "question": ""})
        with patch("core.planner.requests.post", side_effect=[failed, good]) as post:
            planner().plan("x")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["format"], "json")

    def test_prompt_is_small_and_history_is_trimmed(self):
        recent = [{"role": "user", "content": f"question {i}"} for i in range(10)]
        recent[2] = {"role": "assistant", "content": "long brief " * 500}
        recent.append({"role": "user", "content": "now do it"})
        with patch("core.planner.requests.post", return_value=answer({"decision": "chat", "steps": [], "question": ""})) as post:
            planner().plan("now do it", recent)
        payload = post.call_args.kwargs["json"]
        user = payload["messages"][1]["content"]
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertIn("keep_alive", payload)
        self.assertEqual(user.count("Rohan:"), 4)
        self.assertEqual(user.count("now do it"), 1)
        self.assertLess(len(user), 900)


class RunnerOrder(unittest.TestCase):
    def make(self, router_results, plan=None):
        router = MagicMock()
        router.execute.side_effect = list(router_results)
        plan_obj = MagicMock()
        plan_obj.plan.return_value = plan
        runner = IntentRunner(
            router, fast(), plan_obj,
            run_builtin=MagicMock(return_value="builtin done"),
            observer=MagicMock()
        )
        return runner, router, plan_obj

    def test_existing_phrasing_goes_straight_to_the_router(self):
        runner, router, planner_mock = self.make([ToolResult(True, "Opening Notepad.")])
        result = runner.resolve("open notepad")
        self.assertEqual(result.message, "Opening Notepad.")
        router.execute.assert_called_once_with("open notepad")
        planner_mock.plan.assert_not_called()

    def test_site_search_skips_the_router_that_would_google_it(self):
        runner, router, _ = self.make([ToolResult(True, "Opening the website in Opera.")])
        runner.resolve("search youtube for the weeknd")
        router.execute.assert_called_once_with(
            "go to https://www.youtube.com/results?search_query=the+weeknd"
        )

    def test_natural_sentence_is_rewritten_for_the_router(self):
        runner, router, planner_mock = self.make([ToolResult(), ToolResult(True, "Searching.")])
        result = runner.resolve("hey could you google sam altman")
        self.assertTrue(result.success)
        self.assertEqual(router.execute.call_args_list[-1].args[0], "search sam altman")
        planner_mock.plan.assert_not_called()

    def test_multi_step_runs_in_order_and_combines_messages(self):
        runner, router, _ = self.make([ToolResult(True, "Opening Notepad."), ToolResult(True, "Opening Calculator.")])
        result = runner.resolve("open notepad and calculator")
        self.assertEqual(result.message, "Opening Notepad.\nOpening Calculator.")
        self.assertEqual(
            [c.args[0] for c in router.execute.call_args_list],
            ["open notepad", "open calculator"]
        )

    def test_a_failed_step_stops_the_rest(self):
        runner, router, _ = self.make([ToolResult(False, "I couldn't find Opera on your computer.")])
        result = runner.resolve("open youtube and then open notepad")
        self.assertEqual(router.execute.call_count, 1)
        self.assertIn("Opera", result.message)

    def test_plain_chat_is_left_for_the_model(self):
        runner, _, planner_mock = self.make([ToolResult()])
        result = runner.resolve("how are you doing today")
        self.assertFalse(result.success)
        planner_mock.plan.assert_not_called()

    def test_planner_runs_only_for_unrecognised_requests(self):
        plan = MagicMock(kind="act", valid=True, planner_ms=5.0)
        plan.steps = [Step("open_app", "spotify", "open spotify")]
        runner, router, planner_mock = self.make([ToolResult(), ToolResult(True, "Opening Spotify.")], plan)
        result = runner.resolve("can you pop open my music app")
        planner_mock.plan.assert_called_once()
        self.assertEqual(result.message, "Opening Spotify.")

    def test_planner_question_is_returned_to_the_user(self):
        plan = MagicMock(kind="ask", valid=True, planner_ms=5.0, question="Which app?")
        runner, _, _ = self.make([ToolResult()], plan)
        result = runner.resolve("can you open my thing")
        self.assertEqual((result.success, result.message), (True, "Which app?"))

    def test_planner_chat_decision_falls_through_to_conversation(self):
        plan = MagicMock(kind="chat", valid=True, planner_ms=5.0)
        runner, _, _ = self.make([ToolResult()], plan)
        self.assertFalse(runner.resolve("can you pop open my music app").success)

    def test_builtin_steps_use_the_assistant_not_the_router(self):
        plan = MagicMock(kind="act", valid=True, planner_ms=5.0)
        plan.steps = [Step("performance_report", "", "show performance report")]
        runner, router, _ = self.make([ToolResult()], plan)
        result = runner.resolve("can you pop open how you've been doing")
        self.assertEqual(result.message, "builtin done")
        self.assertEqual(router.execute.call_count, 1)

    def test_observation_records_names_not_text(self):
        plan = MagicMock(kind="act", valid=True, planner_ms=5.0)
        plan.steps = [Step("open_app", "spotify", "open spotify")]
        runner, _, _ = self.make([ToolResult(), ToolResult(True, "ok")], plan)
        secret = "can you pop open my private thing"
        runner.resolve(secret)
        event = runner.observer.record_event.call_args.kwargs
        self.assertEqual(event["metadata"]["path"], "planner")
        self.assertEqual(event["metadata"]["actions"], ["open_app"])
        self.assertNotIn(secret, json.dumps(event["metadata"]))

    def test_errors_never_break_the_assistant(self):
        runner, router, _ = self.make([])
        router.execute.side_effect = RuntimeError("boom")
        self.assertFalse(runner.resolve("open notepad").success)


if __name__ == "__main__":
    unittest.main()
