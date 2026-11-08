import unittest
from types import SimpleNamespace

import numpy as np

from core.hotkey import (
    DEFAULT_HOTKEY,
    HotkeyTracker,
    format_hotkey,
    key_name,
    parse_hotkey
)
from voice.utterance_detector import UtteranceDetector


SAMPLERATE = 16000


def noise(seconds, level=0.002, seed=1):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(int(seconds * SAMPLERATE)) * level).astype(
        np.float32
    )


def speech(seconds, amplitude=0.2):
    t = np.arange(int(seconds * SAMPLERATE)) / SAMPLERATE
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def hum(seconds, amplitude=0.0283):
    t = np.arange(int(seconds * SAMPLERATE)) / SAMPLERATE
    return (amplitude * np.sin(2 * np.pi * 50 * t)).astype(np.float32)


def run_detector(detector, audio, chunk=1000):
    """Feed audio in uneven chunks and collect finished utterances."""
    utterances = []
    for start in range(0, len(audio), chunk):
        result = detector.feed(audio[start:start + chunk])
        while result is not None:
            utterances.append(result)
            result = detector.feed(np.zeros(0, dtype=np.float32))
    return utterances


class UtteranceDetectorTests(unittest.TestCase):
    def test_detects_one_spoken_sentence(self):
        audio = np.concatenate([noise(1.0), speech(1.0), noise(1.5)])

        utterances = run_detector(UtteranceDetector(), audio)

        self.assertEqual(len(utterances), 1)
        seconds = len(utterances[0]) / SAMPLERATE
        self.assertGreaterEqual(seconds, 1.0)
        self.assertLessEqual(seconds, 2.0)

    def test_silence_produces_nothing(self):
        utterances = run_detector(UtteranceDetector(), noise(5.0))

        self.assertEqual(utterances, [])

    def test_short_click_is_ignored(self):
        audio = np.concatenate([noise(1.0), speech(0.1, 0.3), noise(1.5)])

        utterances = run_detector(UtteranceDetector(), audio)

        self.assertEqual(utterances, [])

    def test_steady_background_hum_is_not_speech(self):
        audio = np.concatenate([hum(1.0), hum(3.0)])

        utterances = run_detector(UtteranceDetector(), audio)

        self.assertEqual(utterances, [])

    def test_speech_over_background_hum_is_detected(self):
        loud_part = hum(1.0) + speech(1.0)
        audio = np.concatenate([hum(1.0), loud_part, hum(1.5)])

        utterances = run_detector(UtteranceDetector(), audio)

        self.assertEqual(len(utterances), 1)

    def test_finds_several_utterances_in_a_row(self):
        audio = np.concatenate([
            noise(1.0, seed=1), speech(1.0), noise(1.5, seed=2),
            speech(1.0), noise(1.5, seed=3)
        ])

        utterances = run_detector(UtteranceDetector(), audio)

        self.assertEqual(len(utterances), 2)

    def test_very_long_speech_is_cut_at_the_limit(self):
        detector = UtteranceDetector(max_utterance_s=2.0)
        audio = np.concatenate([noise(1.0), speech(5.0)])

        utterances = run_detector(detector, audio)

        self.assertGreaterEqual(len(utterances), 1)
        self.assertLessEqual(len(utterances[0]) / SAMPLERATE, 2.1)

    def test_pause_inside_a_sentence_does_not_split_it(self):
        audio = np.concatenate([
            noise(1.0), speech(0.8), noise(0.5, seed=4), speech(0.8),
            noise(1.5, seed=5)
        ])

        utterances = run_detector(UtteranceDetector(), audio)

        self.assertEqual(len(utterances), 1)
        self.assertGreater(len(utterances[0]) / SAMPLERATE, 2.0)


class ParseHotkeyTests(unittest.TestCase):
    def test_parses_default_hotkey(self):
        modifiers, key = parse_hotkey(DEFAULT_HOTKEY)

        self.assertEqual(modifiers, frozenset({"ctrl", "alt"}))
        self.assertEqual(key, "x")

    def test_is_case_insensitive_and_accepts_control(self):
        modifiers, key = parse_hotkey("Control + ALT + N")

        self.assertEqual(modifiers, frozenset({"ctrl", "alt"}))
        self.assertEqual(key, "n")

    def test_rejects_hotkeys_without_modifier(self):
        with self.assertRaises(ValueError):
            parse_hotkey("x")

    def test_rejects_unknown_modifier(self):
        with self.assertRaises(ValueError):
            parse_hotkey("super+x")

    def test_rejects_modifier_as_final_key(self):
        with self.assertRaises(ValueError):
            parse_hotkey("ctrl+alt")

    def test_formats_a_readable_label(self):
        self.assertEqual(format_hotkey("ctrl+alt+x"), "Ctrl+Alt+X")
        self.assertEqual(format_hotkey("alt+f9"), "Alt+F9")


class KeyNameTests(unittest.TestCase):
    def test_modifier_keys_are_normalised(self):
        for name in ["ctrl", "ctrl_l", "ctrl_r"]:
            self.assertEqual(key_name(SimpleNamespace(name=name)), "ctrl")
        for name in ["alt", "alt_l", "alt_r", "alt_gr"]:
            self.assertEqual(key_name(SimpleNamespace(name=name)), "alt")
        self.assertEqual(key_name(SimpleNamespace(name="shift_r")), "shift")

    def test_special_keys_keep_their_name(self):
        self.assertEqual(key_name(SimpleNamespace(name="esc")), "esc")
        self.assertEqual(key_name(SimpleNamespace(name="f9")), "f9")

    def test_letter_is_found_by_virtual_key_even_with_ctrl_held(self):
        # With Ctrl held, pynput reports a control character, not "x".
        key = SimpleNamespace(vk=88, char="\x18")

        self.assertEqual(key_name(key), "x")

    def test_falls_back_to_the_character(self):
        self.assertEqual(
            key_name(SimpleNamespace(vk=None, char="X")),
            "x"
        )

    def test_unnameable_key_returns_none(self):
        self.assertIsNone(key_name(SimpleNamespace(vk=None, char=None)))


class HotkeyTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = HotkeyTracker("ctrl+alt+x")

    def test_triggers_when_combination_is_pressed(self):
        self.assertFalse(self.tracker.press("ctrl"))
        self.assertFalse(self.tracker.press("alt"))
        self.assertTrue(self.tracker.press("x"))

    def test_modifier_order_does_not_matter(self):
        self.tracker.press("alt")
        self.tracker.press("ctrl")

        self.assertTrue(self.tracker.press("x"))

    def test_plain_x_does_not_trigger(self):
        self.assertFalse(self.tracker.press("x"))

    def test_missing_modifier_does_not_trigger(self):
        self.tracker.press("ctrl")

        self.assertFalse(self.tracker.press("x"))

    def test_extra_modifier_does_not_trigger(self):
        for name in ["ctrl", "alt", "shift"]:
            self.tracker.press(name)

        self.assertFalse(self.tracker.press("x"))

    def test_key_repeat_triggers_only_once(self):
        self.tracker.press("ctrl")
        self.tracker.press("alt")

        self.assertTrue(self.tracker.press("x"))
        self.assertFalse(self.tracker.press("x"))
        self.assertFalse(self.tracker.press("x"))

    def test_can_trigger_again_after_release(self):
        self.tracker.press("ctrl")
        self.tracker.press("alt")
        self.assertTrue(self.tracker.press("x"))

        self.tracker.release("x")

        self.assertTrue(self.tracker.press("x"))

    def test_released_modifier_stops_it_triggering(self):
        self.tracker.press("ctrl")
        self.tracker.press("alt")
        self.tracker.release("alt")

        self.assertFalse(self.tracker.press("x"))

    def test_reset_clears_stuck_keys(self):
        self.tracker.press("ctrl")
        self.tracker.press("alt")

        self.tracker.reset()

        self.assertFalse(self.tracker.press("x"))


if __name__ == "__main__":
    unittest.main()
