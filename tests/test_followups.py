import unittest
from unittest.mock import MagicMock

from core.followups import EXPIRES_AFTER_SECONDS, FollowUps
from core.intent import IntentFastPath, app_targets_from
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

    def test_relative_more_repeats_the_last_volume_direction(self):
        runner, sender = build()

        runner.resolve("increase the volume")
        runner.resolve("a bit more")
        runner.resolve("decrease the volume")
        before = len(sender.pressed)

        result = runner.resolve("a bit more")

        self.assertTrue(result.success)
        self.assertEqual(sender.pressed[before:], [(0xAE, 5)])

    def test_relative_more_tracks_each_direction_change(self):
        runner, sender = build()

        runner.resolve("decrease the volume")
        runner.resolve("a bit more")
        runner.resolve("increase the volume")
        before = len(sender.pressed)

        result = runner.resolve("a bit more")

        self.assertTrue(result.success)
        self.assertEqual(sender.pressed[before:], [(0xAF, 5)])

    def test_volume_followups_accept_natural_more_phrases(self):
        runner, sender = build()
        runner.resolve("turn the volume up")
        before = len(sender.pressed)

        for text in ("a bit more", "a little more", "a little bit more"):
            with self.subTest(text=text):
                self.assertTrue(runner.resolve(text).success, text)

        self.assertEqual(len(sender.pressed) - before, 3)

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
