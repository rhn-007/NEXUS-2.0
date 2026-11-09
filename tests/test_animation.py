import io
import unittest
from unittest.mock import MagicMock, patch

import ui.status as status
from ui.animation import (
    MAX_ANIMATION_SECONDS,
    NexusAnimation,
    SHOW_TIMER_AFTER,
    STILL_WORKING_AFTER
)


class FakeTerminal(io.StringIO):
    def __init__(self, tty=True):
        super().__init__()
        self.tty = tty

    def isatty(self):
        return self.tty


def make_animation(tty=True, columns=80):
    terminal = FakeTerminal(tty)
    animation = NexusAnimation(
        stream=terminal,
        width_provider=lambda: columns
    )
    return animation, terminal


def screen(terminal):
    """Replay carriage returns to get the visible text of the line."""
    line = []
    for char in terminal.getvalue():
        if char == "\r":
            position = 0
            continue
        if "position" not in locals():
            position = 0
        if position < len(line):
            line[position] = char
        else:
            line.append(char)
        position += 1
    return "".join(line).rstrip()


class AnimationTests(unittest.TestCase):
    def setUp(self):
        status.clear_status()

    def tearDown(self):
        status.clear_status()

    def test_original_frames_are_kept(self):
        animation, _ = make_animation()
        self.assertEqual(
            animation.frames,
            ["○──○──●", "○──●──○", "●──○──○", "○──●──○"]
        )

    def test_draws_the_current_activity(self):
        animation, terminal = make_animation()
        status.set_status("Researching")
        animation.draw_once()
        self.assertEqual(
            screen(terminal), "[NEXUS] ○──○──● Researching..."
        )

    def test_nothing_is_drawn_while_idle(self):
        animation, terminal = make_animation()
        animation.draw_once()
        animation.draw_once()
        self.assertEqual(terminal.getvalue(), "")

    def test_line_is_erased_when_status_clears(self):
        animation, terminal = make_animation()
        animation.start = lambda: None
        status.register_clear_hook(animation.erase)
        try:
            status.set_status("Thinking")
            animation.draw_once()
            status.clear_status()
        finally:
            status._clear_hooks.remove(animation.erase)
        self.assertEqual(screen(terminal), "")
        self.assertEqual(animation.drawn_width, 0)

    def test_nothing_more_is_written_after_the_action_ends(self):
        animation, terminal = make_animation()
        status.set_status("Thinking")
        animation.draw_once()
        status.clear_status()
        animation.erase()
        length = len(terminal.getvalue())
        animation.draw_once()
        animation.draw_once()
        self.assertEqual(len(terminal.getvalue()), length)

    def test_no_drawing_when_output_is_not_a_terminal(self):
        animation, terminal = make_animation(tty=False)
        status.set_status("Thinking")
        animation.draw_once()
        self.assertEqual(terminal.getvalue(), "")

    def test_timer_and_still_working_appear_with_age(self):
        animation, _ = make_animation()
        frame = animation.frames[0]
        self.assertNotIn("s", animation.build_line("Researching", 1, frame)[-6:].replace("...", ""))
        self.assertIn(
            f" {SHOW_TIMER_AFTER}s",
            animation.build_line("Researching", SHOW_TIMER_AFTER, frame)
        )
        self.assertIn(
            "(still working)",
            animation.build_line("Researching", STILL_WORKING_AFTER, frame)
        )

    def test_listening_has_no_timer(self):
        animation, _ = make_animation()
        line = animation.build_line("Listening", 500, animation.frames[0])
        self.assertEqual(line, f"[NEXUS] {animation.frames[0]} Listening...")

    def test_line_is_trimmed_to_terminal_width(self):
        animation, _ = make_animation(columns=20)
        line = animation.build_line("A very long activity name", 0, animation.frames[0])
        self.assertLessEqual(len(line), 19)

    def test_safety_timeout_stops_drawing(self):
        animation, terminal = make_animation()
        status.set_status("Researching")
        with patch(
            "ui.animation.get_status_age",
            return_value=MAX_ANIMATION_SECONDS + 1
        ):
            animation.draw_once()
        self.assertEqual(terminal.getvalue(), "")

    def test_shorter_line_leaves_no_leftovers(self):
        animation, terminal = make_animation()
        status.set_status("Researching")
        animation.draw_once()
        with patch("ui.animation.get_status_age", return_value=0):
            status.set_status("Thinking")
            animation.draw_once()
        self.assertEqual(screen(terminal), "[NEXUS] ○──●──○ Thinking...")

    def test_start_and_stop_leave_a_clean_line(self):
        animation, terminal = make_animation()
        status.set_status("Thinking")
        animation.start()
        animation.stop()
        self.assertEqual(screen(terminal), "")


class ActivityTests(unittest.TestCase):
    def setUp(self):
        status.clear_status()

    def tearDown(self):
        status.clear_status()

    def test_previous_status_is_restored(self):
        status.set_status("Thinking")
        with status.activity("Speaking"):
            self.assertEqual(status.get_status(), "Speaking")
        self.assertEqual(status.get_status(), "Thinking")

    def test_status_returns_to_idle_when_there_was_none(self):
        with status.activity("Speaking"):
            pass
        self.assertIsNone(status.get_status())

    def test_status_is_restored_after_an_error(self):
        status.set_status("Thinking")
        with self.assertRaises(RuntimeError):
            with status.activity("Researching"):
                raise RuntimeError("boom")
        self.assertEqual(status.get_status(), "Thinking")

    def test_none_hides_then_resumes(self):
        status.set_status("Researching")
        with status.activity(None):
            self.assertIsNone(status.get_status())
        self.assertEqual(status.get_status(), "Researching")

    def test_hide_erases_the_line_immediately(self):
        animation, terminal = make_animation()
        status.register_clear_hook(animation.erase)
        try:
            status.set_status("Researching")
            animation.draw_once()
            with status.activity(None):
                self.assertEqual(screen(terminal), "")
        finally:
            status._clear_hooks.remove(animation.erase)


class RouterLabelTests(unittest.TestCase):
    def setUp(self):
        status.clear_status()

    def test_labels_are_set_during_a_tool_and_reset_afterwards(self):
        from tools.router import ToolRouter

        seen = {}

        class Tool:
            name = "research"

            def can_handle(self, text):
                return True

            def execute(self, text):
                seen["during"] = status.get_status()
                return "done"

        registry = MagicMock()
        registry.get.return_value = None
        registry.all.return_value = [Tool()]

        status.set_status("Thinking")
        result = ToolRouter(registry).execute("research cats")

        self.assertEqual(seen["during"], "Researching")
        self.assertTrue(result.success)
        self.assertEqual(result.message, "done")
        self.assertEqual(status.get_status(), "Thinking")


if __name__ == "__main__":
    unittest.main()
