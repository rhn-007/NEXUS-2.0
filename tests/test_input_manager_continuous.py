import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch


def load_input_manager():
    """
    Import core.input_manager with stand-ins for pynput and the real
    listener, which need a Windows desktop, a microphone and Whisper.
    """

    fake_pynput = ModuleType("pynput")
    fake_pynput.keyboard = MagicMock()

    fake_listener_module = ModuleType("voice.listener")
    fake_listener_module.Listener = MagicMock()

    stubs = {
        "pynput": fake_pynput,
        "pynput.keyboard": fake_pynput.keyboard,
        "voice.listener": fake_listener_module
    }

    sys.modules.pop("core.input_manager", None)

    with patch.dict(sys.modules, stubs):
        import core.input_manager as module

    return module


input_manager_module = load_input_manager()


def make_manager(listen_results=None):
    manager = input_manager_module.InputManager()
    manager.CONTINUOUS_RESUME_DELAY = 0
    manager.listener = MagicMock()
    manager.listener.listen_for_utterance.side_effect = list(
        listen_results or []
    )
    manager._start_mode_keys = MagicMock()
    manager._stop_mode_keys = MagicMock()
    return manager


class ContinuousInputTests(unittest.TestCase):
    def test_returns_spoken_text_and_marks_input_as_voice(self):
        manager = make_manager(["open notepad"])
        manager.mode = "continuous"

        text = manager.continuous_input()

        self.assertEqual(text, "open notepad")
        self.assertTrue(manager.last_input_was_voice)
        self.assertEqual(manager.mode, "continuous")

    def test_unrecognised_speech_returns_empty_and_stays_in_mode(self):
        manager = make_manager([""])
        manager.mode = "continuous"

        self.assertEqual(manager.continuous_input(), "")
        self.assertEqual(manager.mode, "continuous")
        self.assertFalse(manager.last_input_was_voice)

    def test_toggle_while_listening_returns_to_push_to_talk(self):
        manager = make_manager()
        manager.mode = "continuous"

        # A request made while listening stops the microphone loop.
        def stop_listening(stop_event):
            manager._request_mode("voice")
            return None

        manager.listener.listen_for_utterance.side_effect = stop_listening

        text = manager.continuous_input()

        self.assertEqual(text, "")
        self.assertEqual(manager.mode, "voice")

    def test_toggle_during_a_reply_is_applied_on_next_input(self):
        manager = make_manager(["should not be used"])
        manager.mode = "continuous"

        manager._request_mode("voice")

        text = manager.continuous_input()

        self.assertEqual(text, "")
        self.assertEqual(manager.mode, "voice")
        manager.listener.listen_for_utterance.assert_not_called()

    def test_escape_switches_to_keyboard_mode(self):
        manager = make_manager()
        manager.mode = "continuous"
        manager._request_mode("keyboard")

        manager.continuous_input()

        self.assertEqual(manager.mode, "keyboard")

    def test_text_spoken_just_before_toggle_is_not_lost(self):
        manager = make_manager()
        manager.mode = "continuous"

        def speak_then_toggle(stop_event):
            manager._request_mode("voice")
            return "what time is it"

        manager.listener.listen_for_utterance.side_effect = speak_then_toggle

        text = manager.continuous_input()

        self.assertEqual(text, "what time is it")
        self.assertEqual(manager.mode, "voice")

    def test_microphone_failure_returns_to_push_to_talk(self):
        manager = make_manager()
        manager.mode = "continuous"
        manager.listener.listen_for_utterance.side_effect = RuntimeError(
            "no microphone"
        )

        text = manager.continuous_input()

        self.assertEqual(text, "")
        self.assertEqual(manager.mode, "voice")

    def test_stop_request_does_not_leak_into_the_next_session(self):
        manager = make_manager(["hello"])
        manager.mode = "continuous"
        manager._request_mode("voice")
        manager.continuous_input()
        self.assertFalse(manager.continuous_stop.is_set())

        manager.mode = "continuous"
        self.assertEqual(manager.continuous_input(), "hello")


class GetInputDispatchTests(unittest.TestCase):
    def test_continuous_mode_text_is_returned_to_the_assistant(self):
        manager = make_manager(["open spotify"])
        manager.mode = "continuous"

        self.assertEqual(manager.get_input(), "open spotify")

    def test_spoken_voice_mode_command_leaves_continuous_mode(self):
        manager = make_manager(["voice mode"])
        manager.mode = "continuous"
        manager.voice_input = MagicMock(return_value="hello there")

        text = manager.get_input()

        self.assertEqual(manager.mode, "voice")
        self.assertEqual(text, "hello there")
        manager._stop_mode_keys.assert_called()


class HotkeyConfigTests(unittest.TestCase):
    def test_default_hotkey_is_ctrl_alt_x(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("NEXUS_CONTINUOUS_KEY", None)
            manager = input_manager_module.InputManager()

        self.assertEqual(manager.hotkey_label, "Ctrl+Alt+X")

    def test_hotkey_can_be_changed_with_environment_variable(self):
        with patch.dict("os.environ", {"NEXUS_CONTINUOUS_KEY": "ctrl+alt+n"}):
            manager = input_manager_module.InputManager()

        self.assertEqual(manager.hotkey_label, "Ctrl+Alt+N")

    def test_invalid_setting_falls_back_to_default(self):
        with patch.dict("os.environ", {"NEXUS_CONTINUOUS_KEY": "x"}):
            manager = input_manager_module.InputManager()

        self.assertEqual(manager.hotkey_label, "Ctrl+Alt+X")


if __name__ == "__main__":
    unittest.main()
