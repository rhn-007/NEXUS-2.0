import io
import math
import unittest

from ui.hud_state import (
    STATE_BOOTING,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_SPEAKING,
    STATE_THINKING,
    HudBridge,
    TeeStream,
    clean_text,
    depth_bucket,
    derive_state,
    polar,
    pulse_amount,
    rotate_point,
    sphere_points,
)


class DeriveStateTests(unittest.TestCase):

    def test_booting_wins(self):
        self.assertEqual(
            derive_state("Thinking", speaking=True, booting=True),
            STATE_BOOTING
        )

    def test_idle_with_nothing_happening(self):
        self.assertEqual(derive_state(None), STATE_IDLE)

    def test_thinking_for_work_labels(self):
        for label in ("Thinking", "Researching", "Preparing speech"):
            self.assertEqual(derive_state(label), STATE_THINKING)

    def test_speaking_from_flag_or_label(self):
        self.assertEqual(derive_state(None, speaking=True), STATE_SPEAKING)
        self.assertEqual(derive_state("Speaking"), STATE_SPEAKING)

    def test_listening_from_label_recording_or_continuous_mode(self):
        self.assertEqual(derive_state("Listening"), STATE_LISTENING)
        self.assertEqual(derive_state(None, recording=True), STATE_LISTENING)
        self.assertEqual(
            derive_state(None, mode="continuous"), STATE_LISTENING
        )

    def test_keyboard_and_voice_modes_are_idle_when_quiet(self):
        self.assertEqual(derive_state(None, mode="keyboard"), STATE_IDLE)
        self.assertEqual(derive_state(None, mode="voice"), STATE_IDLE)


class PulseTests(unittest.TestCase):

    def test_range(self):
        for state in (
            STATE_IDLE, STATE_LISTENING, STATE_THINKING,
            STATE_SPEAKING, STATE_BOOTING
        ):
            for step in range(200):
                value = pulse_amount(state, step * 0.05)
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_idle_does_not_pulse(self):
        self.assertEqual(pulse_amount(STATE_IDLE, 3.3), 0.0)


class GlobeTests(unittest.TestCase):

    def test_points_lie_on_unit_sphere(self):
        points = sphere_points(200)
        self.assertEqual(len(points), 200)
        for x, y, z in points:
            self.assertAlmostEqual(math.sqrt(x * x + y * y + z * z), 1.0)

    def test_rotation_keeps_distance_from_center(self):
        for point in sphere_points(50):
            x, y, z = rotate_point(point, 1.3, 0.4)
            self.assertAlmostEqual(math.sqrt(x * x + y * y + z * z), 1.0)

    def test_depth_bucket_edges(self):
        self.assertEqual(depth_bucket(-1.0, 4), 0)
        self.assertEqual(depth_bucket(1.0, 4), 3)
        self.assertEqual(depth_bucket(0.0, 4), 2)

    def test_polar_matches_tk_arc_direction(self):
        x, y = polar(0, 10)
        self.assertAlmostEqual(x, 10)
        self.assertAlmostEqual(y, 0)
        x, y = polar(90, 10)
        self.assertAlmostEqual(x, 0)
        self.assertAlmostEqual(y, -10)


class BridgeTests(unittest.TestCase):

    def test_clean_text_removes_control_codes(self):
        self.assertEqual(clean_text("\x1b[32mhi\x1b[0m\r"), "hi")

    def test_log_is_collected_in_order(self):
        bridge = HudBridge()
        bridge.write_log("one ")
        bridge.write_log("two")
        self.assertEqual(bridge.drain_log(), "one two")
        self.assertEqual(bridge.drain_log(), "")

    def test_speaking_counts_nested_calls(self):
        bridge = HudBridge()
        bridge.begin_speaking()
        bridge.begin_speaking()
        bridge.end_speaking()
        self.assertTrue(bridge.speaking)
        bridge.end_speaking()
        self.assertFalse(bridge.speaking)
        bridge.end_speaking()
        self.assertFalse(bridge.speaking)

    def test_booting_until_ready(self):
        bridge = HudBridge()
        self.assertTrue(bridge.booting)
        bridge.set_ready()
        self.assertFalse(bridge.booting)


class TeeStreamTests(unittest.TestCase):

    def test_text_reaches_both_places(self):
        terminal = io.StringIO()
        bridge = HudBridge()
        tee = TeeStream(terminal, bridge)
        tee.write("hello\n")
        self.assertEqual(terminal.getvalue(), "hello\n")
        self.assertEqual(bridge.drain_log(), "hello\n")

    def test_works_without_a_terminal(self):
        bridge = HudBridge()
        tee = TeeStream(None, bridge)
        self.assertEqual(tee.write("hi"), 2)
        self.assertEqual(bridge.drain_log(), "hi")
        self.assertFalse(tee.isatty())


if __name__ == "__main__":
    unittest.main()
