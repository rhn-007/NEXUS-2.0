import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.prompts import SYSTEM_PROMPT
from core import capabilities
from core.intent import IntentFastPath
from core.intent_runner import IntentRunner
from tools.router import ToolResult
from tools.system_info import detect_topics


class Answers(unittest.TestCase):
    def test_overview_lists_every_capability(self):
        text = capabilities.answer("what can you do")
        for name, _, example in capabilities.CAPABILITIES:
            self.assertIn(name, text)
            self.assertIn(example, text)

    def test_other_ways_of_asking(self):
        for text in ["what are your capabilities", "what all can u do",
                     "what are you capable of", "how can you help me"]:
            self.assertIn("what I can do", capabilities.answer(text), text)

    def test_limits_overview(self):
        for text in ["what can't you do", "what are your limitations", "what can you not do"]:
            self.assertIn("can't do yet", capabilities.answer(text), text)

    def test_can_you_something_unsupported_is_a_plain_no(self):
        for text in ["can you send an email", "can you set a reminder",
                     "could you take a screenshot", "can you shut down the pc"]:
            self.assertIn("can't do that yet", capabilities.answer(text), text)

    def test_things_it_can_do_are_not_answered_here(self):
        for text in ["can you open notepad", "can you check my battery",
                     "can you play the next song"]:
            self.assertIsNone(capabilities.answer(text), text)

    def test_questions_about_a_topic_are_left_to_the_model(self):
        for text in ["can you explain how to delete a file",
                     "tell me about email",
                     "what is the volume of a sphere"]:
            self.assertIsNone(capabilities.answer(text), text)


class Prompt(unittest.TestCase):
    def test_prompt_lists_can_and_cannot(self):
        self.assertNotIn("@@CAPABILITIES@@", SYSTEM_PROMPT)
        for _, what, _ in capabilities.CAPABILITIES:
            self.assertIn(what, SYSTEM_PROMPT)
        for what, _ in capabilities.LIMITS:
            self.assertIn(what, SYSTEM_PROMPT)

    def test_personality_text_is_untouched(self):
        self.assertIn("You are NEXUS, Rohan's personal AI assistant.", SYSTEM_PROMPT)
        self.assertIn("OVERALL BEHAVIOR:", SYSTEM_PROMPT)

    def test_every_example_is_something_it_really_understands(self):
        # The examples shown to the user must work as typed.
        fast = IntentFastPath(["youtube", "github"], ["notepad"])
        for name, _, example in capabilities.CAPABILITIES:
            if name in ("Conversation", "Research"):
                continue
            understood = (fast.fast_steps(example) or detect_topics(example)
                          or fast.builtin_command(example))
            self.assertTrue(understood, example)


class RunnerHook(unittest.TestCase):
    def test_runner_answers_without_the_router_or_model(self):
        router, planner = MagicMock(), MagicMock()
        runner = IntentRunner(router, IntentFastPath([], []), planner, MagicMock(), MagicMock())
        result = runner.resolve("what can you do")
        self.assertTrue(result.success)
        self.assertIn("what I can do", result.message)
        router.execute.assert_not_called()
        planner.plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
