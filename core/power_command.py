"""Explicit, confirmation-based Windows shutdown phrase handling."""

import re
import subprocess
import time


class ShutdownPhraseHandler:
    """Handle an exact trigger, a time-limited confirmation, and cancellation."""

    CONFIRMATION_TIMEOUT_SECONDS = 15

    def __init__(self, runner=None, clock=None, platform_name=None):
        self.runner = runner or subprocess.run
        self.clock = clock or time.monotonic
        self.platform_name = platform_name
        self.pending_since = None
        self.shutdown_scheduled = False

    @staticmethod
    def _normalise(text):
        text = str(text or "").lower().replace("’", "'")
        text = re.sub(r"[^a-z\s]", " ", text)
        return " ".join(text.split())

    def _is_windows(self):
        if self.platform_name is not None:
            return self.platform_name == "win32"
        import sys
        return sys.platform == "win32"

    def handle(self, text):
        """Return a response for a recognised command, otherwise None."""
        command = self._normalise(text)

        if self.pending_since is not None:
            if self.clock() - self.pending_since > self.CONFIRMATION_TIMEOUT_SECONDS:
                self.pending_since = None
                return "The shutdown confirmation expired. Nothing was shut down."

        if command == "green apple":
            self.pending_since = self.clock()
            return (
                "Do you want me to shut down this computer? "
                "Say confirm within 15 seconds, or say cancel."
            )

        if command == "confirm":
            if self.pending_since is None:
                return None
            self.pending_since = None
            if not self._is_windows():
                return "Computer shutdown is only supported on Windows."
            try:
                self.runner(
                    ["shutdown", "/s", "/t", "30"],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except (OSError, subprocess.CalledProcessError) as error:
                return f"I couldn't schedule the shutdown: {error}"
            self.shutdown_scheduled = True
            return (
                "Shutdown is scheduled in 30 seconds. "
                "Say cancel shutdown if you change your mind."
            )

        if command in ("cancel", "cancel shutdown", "never mind"):
            if self.pending_since is not None:
                self.pending_since = None
                return "Shutdown cancelled. Your computer will stay on."
            if self.shutdown_scheduled:
                if not self._is_windows():
                    return "I can't cancel the scheduled shutdown on this system."
                try:
                    self.runner(
                        ["shutdown", "/a"],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                except (OSError, subprocess.CalledProcessError) as error:
                    return f"I couldn't cancel the scheduled shutdown: {error}"
                self.shutdown_scheduled = False
                return "The scheduled shutdown has been cancelled."

        # While awaiting confirmation, keep unrelated speech away from the
        # language model so it cannot claim that a shutdown was initiated.
        if self.pending_since is not None:
            return "Please say confirm to schedule the shutdown, or cancel to keep this computer on."

        return None
