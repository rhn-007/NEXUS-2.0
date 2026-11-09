import shutil
import sys
import threading
import time

from ui.status import get_status, get_status_age, register_clear_hook


# After this many seconds an action shows how long it has been running.
SHOW_TIMER_AFTER = 5

# After this many seconds the line also says NEXUS is still working.
STILL_WORKING_AFTER = 20

# Safety net: stop drawing if a status is never cleared.
MAX_ANIMATION_SECONDS = 600

# Waiting states that are not "work in progress": no timer, no timeout.
WAITING_LABELS = ("Listening",)


class NexusAnimation:

    def __init__(self, stream=None, width_provider=None):

        self.running = False

        self.thread = None

        self.stream = stream

        self.width_provider = width_provider

        # Guards every write so the loop and clear_line() never interleave.
        self.lock = threading.RLock()

        # Characters currently on screen from the animation, so exactly
        # that much is erased and nothing else on the line is disturbed.
        self.drawn_width = 0

        self.frames = [

            "○──○──●",

            "○──●──○",

            "●──○──○",

            "○──●──○"

        ]

        self.index = 0

    # ======================================================
    # TERMINAL HELPERS
    # ======================================================

    def _stream(self):

        return self.stream or sys.stdout

    def _is_terminal(self):

        try:

            return bool(self._stream().isatty())

        except Exception:

            return False

    def _columns(self):

        if self.width_provider:

            return self.width_provider()

        return shutil.get_terminal_size((80, 24)).columns

    # ======================================================
    # TEXT
    # ======================================================

    def build_line(self, status, age, frame):

        text = f"[NEXUS] {frame} {status}..."

        if status not in WAITING_LABELS:

            if age >= SHOW_TIMER_AFTER:

                text += f" {int(age)}s"

            if age >= STILL_WORKING_AFTER:

                text += " (still working)"

        # Keep the line shorter than the terminal so it never wraps.
        limit = max(self._columns() - 1, 10)

        if len(text) > limit:

            text = text[:limit]

        return text

    # ======================================================
    # DRAWING
    # ======================================================

    def start(self):

        if self.running:

            return

        self.running = True

        self.thread = threading.Thread(

            target=self.loop,

            daemon=True

        )

        self.thread.start()

    def draw_once(self):
        """One refresh: draw the current status, or erase if there is none."""

        with self.lock:

            # Read the status while holding the lock, so a status cleared
            # a moment ago is never drawn.
            status = get_status()

            if not status or not self._is_terminal():

                self.erase()

                return

            age = get_status_age()

            if (
                status not in WAITING_LABELS
                and age > MAX_ANIMATION_SECONDS
            ):

                self.erase()

                return

            line = self.build_line(
                status,
                age,
                self.frames[self.index]
            )

            self.index = (self.index + 1) % len(self.frames)

            # Pad when the new line is shorter than the previous one.
            padding = " " * max(self.drawn_width - len(line), 0)

            stream = self._stream()

            # Draw, then return to the start of the line so normal output
            # lands cleanly.
            stream.write("\r" + line + padding + "\r")

            stream.flush()

            self.drawn_width = len(line)

    def loop(self):

        while self.running:

            self.draw_once()

            time.sleep(0.25)

    def erase(self):
        """Remove the animation line, only if something was drawn."""

        with self.lock:

            if self.drawn_width <= 0:

                return

            stream = self._stream()

            stream.write(
                "\r" + (" " * self.drawn_width) + "\r"
            )

            stream.flush()

            self.drawn_width = 0

    def clear_line(self):

        self.erase()

    def stop(self):

        self.running = False

        if self.thread:

            self.thread.join(

                timeout=1

            )

            self.thread = None

        self.erase()


animation = NexusAnimation()

# Erase the line the moment a status is cleared.
register_clear_hook(animation.erase)
