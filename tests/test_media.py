import json
import unittest
from unittest.mock import MagicMock, patch

from core.intent import IntentFastPath, app_targets_from
from core.intent_runner import IntentRunner
from core.planner import IntentPlanner
from tools.media import (
    KEY_CODES,
    KeySender,
    MAX_PRESSES,
    MediaTool,
    MediaUnavailable,
    detect_media
)


def first(text):
    found = detect_media(text)
    return found[0] if found else None


class UnderstandsMediaRequests(unittest.TestCase):
    def test_playback(self):
        for text in [
            "play the current song on spotify", "pause the music",
            "pause the music please", "resume the song", "stop the music",
            "play music", "play some music", "pause spotify",
            "can you pause the video", "hey nexus, resume the podcast",
        ]:
            self.assertEqual(first(text), ("play_pause", ""), text)

    def test_next_and_previous(self):
        for text in ["next song", "skip this track", "skip the song",
                     "play the next song", "skip to the next track"]:
            self.assertEqual(first(text), ("next", ""), text)
        for text in ["previous song", "go back a song", "play the last track",
                     "play the previous song"]:
            self.assertEqual(first(text), ("previous", ""), text)

    def test_volume(self):
        for text in ["volume up", "turn it up", "turn up the volume",
                     "make it louder", "a bit louder", "increase the volume"]:
            self.assertEqual(first(text), ("volume_up", ""), text)
        for text in ["volume down", "turn it down", "turn the music down",
                     "lower the volume", "make it quieter", "a little quieter"]:
            self.assertEqual(first(text), ("volume_down", ""), text)
        for text in ["mute the sound", "mute the pc", "unmute the volume",
                     "turn the sound off"]:
            self.assertEqual(first(text), ("mute", ""), text)

    def test_exact_volume(self):
        self.assertEqual(first("set the volume to 40"), ("set_volume", "40"))
        self.assertEqual(first("put the volume at 25 percent"), ("set_volume", "25"))
        self.assertEqual(first("volume to 70"), ("set_volume", "70"))
        self.assertEqual(first("set volume to 150"), ("set_volume", "100"))

    def test_several_in_one_sentence(self):
        self.assertEqual(
            detect_media("pause the music and mute the sound"),
            [("play_pause", ""), ("mute", "")]
        )

    def test_typed_command_form(self):
        self.assertEqual(first("media next"), ("next", ""))
        self.assertEqual(first("media volume 30"), ("set_volume", "30"))
        self.assertEqual(detect_media("media volume 999x"), [])

    def test_everything_else_is_left_alone(self):
        for text in [
            "play the guitar", "my next meeting", "what's the next song",
            "volume of a sphere", "skip the intro of my essay",
            "the song is great", "play despacito", "tell me about music",
            "i need to pause and think", "what is the next step",
            # Bare words could come from background speech.
            "next", "pause", "mute", "play", "louder",
        ]:
            self.assertEqual(detect_media(text), [], text)


class FakeSender:
    def __init__(self):
        self.pressed = []

    def press(self, key_code, count=1):
        self.pressed.append((key_code, count))


class ToolSendsOnlyMediaKeys(unittest.TestCase):
    def ask(self, text):
        sender = FakeSender()
        result = MediaTool(sender).execute(text)
        return result, sender.pressed

    def test_single_key_actions(self):
        for text, key, message in [
            ("pause the music", "play_pause", "Pressed play/pause."),
            ("next song", "next", "Next track."),
            ("previous song", "previous", "Previous track."),
        ]:
            result, pressed = self.ask(text)
            self.assertEqual(pressed, [(KEY_CODES[key], 1)])
            self.assertEqual(result.message, message)

    def test_volume_nudges(self):
        _, up = self.ask("turn it up")
        self.assertEqual(up, [(KEY_CODES["volume_up"], 5)])
        _, down = self.ask("turn it down")
        self.assertEqual(down, [(KEY_CODES["volume_down"], 5)])

    def test_mute_says_it_toggles(self):
        result, pressed = self.ask("mute the sound")
        self.assertEqual(pressed, [(KEY_CODES["mute"], 1)])
        self.assertIn("toggles", result.message)

    def test_exact_volume_goes_to_zero_then_up(self):
        result, pressed = self.ask("set the volume to 40")
        self.assertEqual(
            pressed,
            [(KEY_CODES["volume_down"], MAX_PRESSES), (KEY_CODES["volume_up"], 20)]
        )
        self.assertEqual(result.message, "Volume set to about 40%.")

    def test_volume_zero_and_hundred(self):
        _, zero = self.ask("set the volume to 0")
        self.assertEqual(zero, [(KEY_CODES["volume_down"], MAX_PRESSES)])
        _, full = self.ask("set the volume to 100")
        self.assertEqual(full[1], (KEY_CODES["volume_up"], 50))

    def test_only_known_media_keys_exist(self):
        self.assertEqual(
            sorted(KEY_CODES.values()),
            [0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB3]
        )

    def test_errors_are_reported_not_hidden(self):
        sender = MagicMock()
        sender.press.side_effect = MediaUnavailable("Media keys only work on Windows.")
        result = MediaTool(sender).execute("next song")
        self.assertFalse(result.success)
        self.assertIn("Windows", result.message)

        sender.press.side_effect = OSError("denied")
        result = MediaTool(sender).execute("next song")
        self.assertFalse(result.success)
        self.assertIn("couldn't", result.message)

    def test_sender_refuses_off_windows(self):
        with patch("tools.media.sys.platform", "linux"):
            with self.assertRaises(MediaUnavailable):
                KeySender().press(KEY_CODES["next"])

    def test_unrelated_text_is_not_handled(self):
        self.assertFalse(MediaTool(FakeSender()).can_handle("tell me a story"))


class IntegrationWithIntentLayer(unittest.TestCase):
    def runner(self, planner=None):
        from tools.application import ApplicationTool
        from tools.browser import BrowserTool
        from tools.registry import ToolRegistry
        from tools.router import ToolRouter

        self.sender = FakeSender()
        registry = ToolRegistry()
        browser = BrowserTool()
        registry.register(browser)
        registry.register(ApplicationTool())
        registry.register(MediaTool(self.sender))
        router = ToolRouter(registry)
        fast = IntentFastPath(
            list(browser.websites),
            app_targets_from(registry.get("application"))
        )
        return IntentRunner(router, fast, planner or MagicMock(), MagicMock(), MagicMock())

    def test_the_message_that_failed_on_the_real_machine(self):
        planner = MagicMock()
        result = self.runner(planner).resolve("play the current song on spotify")
        self.assertEqual(result.message, "Pressed play/pause.")
        self.assertEqual(self.sender.pressed, [(KEY_CODES["play_pause"], 1)])
        planner.plan.assert_not_called()

    def test_opening_spotify_still_opens_it(self):
        from tools.application import ApplicationTool

        runner = self.runner()
        with patch.object(ApplicationTool, "execute", return_value="Opening Spotify."):
            result = runner.resolve("open spotify")
        self.assertEqual(result.message, "Opening Spotify.")
        self.assertEqual(self.sender.pressed, [])

    def test_two_media_requests_then_an_app(self):
        runner = self.runner()
        result = runner.resolve("next song and turn it up")
        self.assertEqual(result.message, "Next track.\nVolume up.")
        self.assertEqual(
            self.sender.pressed,
            [(KEY_CODES["next"], 1), (KEY_CODES["volume_up"], 5)]
        )

    def test_polite_wording(self):
        result = self.runner().resolve("hey nexus could you please set the volume to 30")
        self.assertEqual(result.message, "Volume set to about 30%.")


def plan_for(step, text):
    planner = IntentPlanner("u", "m", ["youtube"], ["notepad"])
    response = MagicMock()
    response.ok = True
    response.json.return_value = {"message": {"content": json.dumps(
        {"decision": "act", "steps": [step], "question": ""})}}
    with patch("core.planner.requests.post", return_value=response):
        return planner.plan(text)


class PlannerMedia(unittest.TestCase):
    def test_valid_choices(self):
        for value, command in [
            ("next", "media next"),
            ("volume_down", "media volume_down"),
            ("volume 40", "media volume 40"),
        ]:
            plan = plan_for({"action": "media", "value": value}, "play something quieter on my music")
            self.assertEqual([s.command for s in plan.steps], [command])

    def test_invalid_values_are_rejected(self):
        for value in ["volume 400", "format c:", "next; del *", "volume", ""]:
            plan = plan_for({"action": "media", "value": value}, "turn the music up a notch")
            self.assertEqual(plan.kind, "chat", value)

    def test_unrelated_requests_do_not_become_media_keys(self):
        plan = plan_for({"action": "media", "value": "play_pause"}, "play the guitar for me")
        self.assertEqual(plan.kind, "chat")


if __name__ == "__main__":
    unittest.main()
