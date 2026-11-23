import unittest
from unittest.mock import MagicMock

from core.followups import EXPIRES_AFTER_SECONDS, FollowUps
from core.intent import IntentFastPath, Step, app_targets_from
from core.intent_runner import IntentRunner
from tests.test_media import FakeSender
from tests.test_system_info import GB, FakeReader
from tools.application import ApplicationTool
from tools.browser import BrowserTool
from tools.media import MediaTool
from tools.registry import ToolRegistry
from tools.router import ToolRouter
from tools.system_info import SystemInfoTool


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def build(clock=None, **values):
    registry = ToolRegistry()
    browser = BrowserTool()
    sender = FakeSender()
    registry.register(browser)
    registry.register(ApplicationTool())
    registry.register(SystemInfoTool(FakeReader(**values)))
    registry.register(MediaTool(sender))
    fast = IntentFastPath(list(browser.websites), app_targets_from(registry.get("application")))
    runner = IntentRunner(ToolRouter(registry), fast, MagicMock(), MagicMock(), MagicMock())
    if clock:
        runner.followups = FollowUps(clock)
    return runner, sender


FULL_DISK = dict(disks=[("C", 200 * GB, 4 * GB), ("D", 276 * GB, 169 * GB)])


class ContextualReferenceFollowUps(unittest.TestCase):
    def test_contextual_search_is_deferred_to_planner(self):
        runner, _ = build()
        from tools.router import ToolResult

        runner.history = None
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Searching for The Weeknd.")
        )
        recent = [
            {"role": "user", "content": "The Weeknd is my favourite singer."},
            {"role": "assistant", "content": "I'll keep that in mind."}
        ]
        plan = MagicMock(
            kind="act",
            valid=True,
            planner_ms=1.0,
            expects="",
            steps=[Step("web_search", "The Weeknd popular songs", "search The Weeknd popular songs")]
        )
        runner.planner.plan.return_value = plan

        result = runner.resolve("find his most popular songs", recent)

        self.assertTrue(result.success)
        runner.planner.plan.assert_called_once_with(
            "find his most popular songs", recent
        )
        self.assertEqual(
            runner.router.execute.call_args.args[0],
            "search The Weeknd popular songs"
        )

    def test_site_search_with_pronoun_uses_the_known_subject(self):
        from tools.router import ToolResult

        runner, _ = build()
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Searching Spotify for The Weeknd.")
        )
        recent = [
            {"role": "user", "content": "The Weeknd is my favourite singer."}
        ]

        self.assertEqual(
            runner.fast.fast_steps("search him up on Spotify"),
            []
        )
        result = runner.resolve("search him up on Spotify", recent)

        self.assertTrue(result.success)
        runner.router.execute.assert_called_once_with("spotify search the weeknd")
        runner.planner.plan.assert_not_called()



class ConversationContextRouting(unittest.TestCase):
    def test_contextual_action_uses_recent_conversation_before_router(self):
        runner, _ = build()
        from tools.router import ToolResult

        runner.history = None
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Opened the selected result.")
        )
        recent = [
            {"role": "user", "content": "Find beginner robotics projects."},
            {
                "role": "assistant",
                "content": "Here are three options: 1. Arduino rover "
                           "(https://example.com/rover), 2. Line follower "
                           "(https://example.com/line), 3. Robotic arm "
                           "(https://example.com/arm)."
            }
        ]
        plan = MagicMock(
            kind="act",
            valid=True,
            planner_ms=1.0,
            expects="",
            steps=[
                Step(
                    "open_website",
                    "https://example.com/line",
                    "go to https://example.com/line"
                )
            ]
        )
        runner.planner.plan.return_value = plan

        result = runner.resolve("open the second one", recent)

        self.assertTrue(result.success)
        runner.planner.plan.assert_called_once_with(
            "open the second one", recent
        )
        runner.router.execute.assert_called_once_with(
            "go to https://example.com/line"
        )

    def test_contextual_action_without_recent_context_uses_normal_fallback(self):
        runner, _ = build()

        runner.resolve("open the second one")

        runner.planner.plan.assert_called_once_with(
            "open the second one", None
        )

    def test_explicit_new_request_keeps_existing_fast_path(self):
        runner, _ = build()

        self.assertFalse(
            runner._needs_conversation_context("open notepad")
        )
        self.assertTrue(runner.fast.fast_steps("open notepad"))

    def test_search_refinement_reuses_the_previous_search_topic(self):
        from tools.router import ToolResult

        runner, _ = build()
        runner.history = None
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Searching Google for beginner-friendly robotics projects.")
        )
        recent = [
            {"role": "user", "content": "Find beginner robotics projects."},
            {"role": "assistant", "content": "Searching Google for beginner robotics projects."}
        ]

        result = runner.resolve("Show me beginner-friendly ones.", recent)

        self.assertTrue(result.success)
        runner.router.execute.assert_called_once_with(
            "search beginner-friendly robotics projects"
        )
        runner.planner.plan.assert_not_called()

    def test_search_refinement_is_generic_and_needs_a_prior_search(self):
        recent = [
            {"role": "user", "content": "Find affordable laptops."},
            {"role": "assistant", "content": "Searching Google for affordable laptops."}
        ]

        self.assertEqual(
            IntentRunner._search_refinement("Show me cheaper ones", recent),
            "cheaper laptops"
        )
        self.assertIsNone(
            IntentRunner._search_refinement("Show me cheaper ones", [])
        )

        stale_context = [
            {"role": "user", "content": "Find beginner robotics projects."},
            {"role": "assistant", "content": "Searching Google for beginner robotics projects."},
            {"role": "user", "content": "Let's talk about the weather."},
            {"role": "assistant", "content": "Sure, what about it?"},
            {"role": "user", "content": "Show me cheaper ones"}
        ]
        self.assertIsNone(
            IntentRunner._search_refinement("Show me cheaper ones", stale_context)
        )


    def test_contextual_pronoun_search_uses_known_subject_on_spotify(self):
        from tools.router import ToolResult

        runner, _ = build()
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Searching Spotify for The Weeknd.")
        )
        recent = [
            {"role": "user", "content": "Who is my favourite music artist?"},
            {"role": "assistant", "content": "Your favourite singer is The Weeknd."}
        ]

        result = runner.resolve("Can you search him up on Spotify?", recent)

        self.assertTrue(result.success)
        runner.router.execute.assert_called_once_with("spotify search the weeknd")
        runner.planner.plan.assert_not_called()

    def test_contextual_search_without_destination_keeps_previous_destination(self):
        from tools.router import ToolResult

        runner, _ = build()
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Searching Spotify for The Weeknd.")
        )
        recent = [
            {"role": "user", "content": "Who is my favourite music artist?"},
            {"role": "assistant", "content": "Your favourite singer is The Weeknd."},
            {"role": "user", "content": "Can you search him up on Spotify?"},
            {"role": "assistant", "content": "Searching Spotify for The Weeknd."}
        ]

        result = runner.resolve("Now search him up.", recent)

        self.assertTrue(result.success)
        runner.router.execute.assert_called_once_with("spotify search the weeknd")
        runner.planner.plan.assert_not_called()

    def test_explicit_browser_destination_overrides_previous_spotify_search(self):
        from tools.router import ToolResult

        runner, _ = build()
        runner.router.execute = MagicMock(
            return_value=ToolResult(True, "Searching Google for The Weeknd.")
        )
        recent = [
            {"role": "assistant", "content": "Your favourite singer is The Weeknd."},
            {"role": "user", "content": "Can you search him up on Spotify?"},
            {"role": "assistant", "content": "Searching Spotify for The Weeknd."}
        ]

        result = runner.resolve("Search him up on the browser.", recent)

        self.assertTrue(result.success)
        runner.router.execute.assert_called_once_with("search the weeknd")
        runner.planner.plan.assert_not_called()


class AnythingElse(unittest.TestCase):
    def test_walks_through_new_information_then_ends(self):
        runner, _ = build(**FULL_DISK)
        first = runner.resolve("how is my pc doing")
        self.assertIn("Heads up", first.message)
        second = runner.resolve("anything else?")
        self.assertIn("Using the most memory", second.message)
        third = runner.resolve("what else?")
        # The summary already showed disk, battery, cpu, memory and uptime.
        self.assertTrue(third.message.startswith("The Wi-Fi") or "Home" in third.message, third.message)
        last = runner.resolve("anything else")
        self.assertTrue(last.message.startswith("That's everything I can see on your PC."))
        self.assertIn("C: is almost full", last.message)

    def test_never_repeats_the_same_answer(self):
        runner, _ = build()
        seen = []
        for text in ["how is my pc doing", "anything else", "anything else", "anything else"]:
            seen.append(runner.resolve(text).message)
        self.assertEqual(len(set(seen)), len(seen))
        self.assertTrue(seen[-1].startswith("That's everything"))
        self.assertEqual(runner.resolve("anything else").message, seen[-1])

    def test_after_a_single_reading_it_gives_other_readings(self):
        runner, _ = build()
        runner.resolve("what's my cpu usage")
        answer = runner.resolve("anything else?")
        # A single CPU reading has not covered the rest, so the overview comes next.
        self.assertIn("PC status", answer.message)

    def test_tell_me_more_works_the_same_way(self):
        runner, _ = build()
        runner.resolve("how is my pc doing")
        self.assertIn("Using the most memory", runner.resolve("tell me more").message)

    def test_media_and_meeting_contexts(self):
        runner, _ = build()
        runner.resolve("volume up")
        self.assertIn("next or previous track", runner.resolve("anything else?").message)
        runner.followups.note("meeting", "start_meeting", "start meeting")
        self.assertIn("Google Meet", runner.resolve("anything else?").message)

    def test_without_context_it_is_left_for_the_model(self):
        runner, _ = build()
        result = runner.resolve("anything else?")
        self.assertFalse(result.success)

    def test_expires_after_a_few_minutes(self):
        clock = Clock()
        runner, _ = build(clock)
        runner.resolve("how is my pc doing")
        clock.now += EXPIRES_AFTER_SECONDS + 1
        self.assertFalse(runner.resolve("anything else?").success)

    def test_plain_conversation_ends_the_context(self):
        runner, _ = build()
        runner.resolve("how is my pc doing")
        runner.resolve("tell me a story about a dragon")
        self.assertFalse(runner.resolve("anything else?").success)


class PcFollowUps(unittest.TestCase):
    def setUp(self):
        self.runner, _ = build(
            battery={"has_battery": True, "percent": 100, "charging": True}, **FULL_DISK
        )
        self.runner.resolve("how is my pc doing")

    def test_other_topics(self):
        for text, expected in [
            ("and the battery?", "100%"),
            ("what about the cpu?", "CPU usage is 14%"),
            ("how about the D drive?", "D: 169 GB free"),
            ("and the memory", "8.0 GB of 16.0 GB"),
            ("which one is using the most?", "Using the most memory"),
        ]:
            self.assertIn(expected, self.runner.resolve(text).message, text)

    def test_is_that_bad_explains_with_real_numbers(self):
        self.runner.resolve("how much space is left on my drive")
        answer = self.runner.resolve("is that bad?")
        self.assertIn("C: has only 4.0 GB free", answer.message)
        self.assertIn("Disk Cleanup", answer.message)

    def test_explaining_a_healthy_reading(self):
        self.runner.resolve("what's my cpu usage")
        self.assertEqual(self.runner.resolve("why?").message, "No, the CPU load is normal.")

    def test_new_subjects_are_not_follow_ups(self):
        for text in [
            "what about the volume of a sphere",
            "and the weather in paris",
            "what about my project deadline",
            "how about we talk about dragons",
        ]:
            self.assertFalse(self.runner.resolve(text).success, text)
            self.runner.resolve("how is my pc doing")


class MediaAndMeetingFollowUps(unittest.TestCase):
    def test_louder_lower_and_again(self):
        runner, sender = build()
        runner.resolve("turn the volume up")
        before = len(sender.pressed)
        self.assertTrue(runner.resolve("a bit louder").success)
        self.assertTrue(runner.resolve("lower it more").success)
        self.assertTrue(runner.resolve("again").success)
        self.assertEqual(len(sender.pressed) - before, 3)

    def test_volume_followups_accept_longer_natural_phrasing(self):
        runner, sender = build()
        runner.resolve("turn the volume up")
        before = len(sender.pressed)

        for text in (
            "a bit more",
            "a little more",
            "a little bit more",
            "increase it a bit more",
            "increase the volume a bit more",
            "turn the volume up a bit more",
        ):
            with self.subTest(text=text):
                self.assertTrue(runner.resolve(text).success, text)

        self.assertEqual(len(sender.pressed) - before, 6)

    def test_relative_more_repeats_the_last_volume_direction(self):
        runner, sender = build()

        runner.resolve("increase the volume")
        runner.resolve("a bit more")
        runner.resolve("decrease the volume")
        before = len(sender.pressed)

        result = runner.resolve("a bit more")

        self.assertTrue(result.success)
        self.assertEqual(
            sender.pressed[before:],
            [(0xAE, 5)],
            "After decreasing volume, relative 'more' must continue decreasing."
        )

    def test_relative_more_tracks_each_direction_change(self):
        runner, sender = build()

        runner.resolve("decrease the volume")
        runner.resolve("a bit more")
        runner.resolve("increase the volume")
        before = len(sender.pressed)

        result = runner.resolve("a bit more")

        self.assertTrue(result.success)
        self.assertEqual(sender.pressed[before:], [(0xAF, 5)])

    def test_volume_followup_requires_existing_media_context(self):
        runner, _ = build()
        self.assertFalse(runner.resolve("increase it a bit more").success)

    def test_next_one_after_a_media_action(self):
        runner, _ = build()
        runner.resolve("turn the volume up")
        result = runner.resolve("and the next one")
        self.assertTrue(result.success)

    def test_louder_means_nothing_without_a_volume_context(self):
        runner, _ = build()
        runner.resolve("how is my pc doing")
        self.assertFalse(runner.resolve("louder").success)

    def test_another_meeting(self):
        runner, _ = build()
        runner.followups.note("meeting", "start_meeting", "start meeting")
        runner._run_steps = MagicMock(return_value="started")
        self.assertEqual(runner.resolve("start another one"), "started")
        step = runner._run_steps.call_args[0][0][0]
        self.assertEqual(step.action, "start_meeting")


if __name__ == "__main__":
    unittest.main()
