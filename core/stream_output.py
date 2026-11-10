"""
NEXUS Stream Output

Shows a reply on screen sentence by sentence while the model is still
writing it, and starts speaking the first sentence early. Nothing here
changes what is stored: the assistant still keeps the finished reply.
"""

import re
import sys
import threading

from ui.status import clear_status
from utils.logger import setup_logger


logger = setup_logger(__name__)


# A sentence ends at . ! or ? followed by whitespace, or at a line break.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")

# Too short to be worth speaking on its own ("1." or "Sure.").
MIN_EARLY_WORDS = 4


class StreamPresenter:

    def __init__(self, speaker, refine=None, write=None):

        self.speaker = speaker
        self.refine = refine or (lambda text: text)
        self.write = write or self._stdout

        self.raw = ""            # everything received so far
        self.shown = 0           # characters of raw already handled
        self.displayed = False   # has anything been written to the screen
        self.spoken_raw = ""     # raw text already spoken early
        self.thread = None
        self.lock = threading.Lock()

    @staticmethod
    def _stdout(text):

        sys.stdout.write(text)
        sys.stdout.flush()

    # ------------------------------------------------------
    # INCOMING TEXT
    # ------------------------------------------------------

    def feed(self, piece):

        with self.lock:

            self.raw += piece

            while True:

                match = _BOUNDARY.search(self.raw, self.shown)

                # A boundary at the very end may still grow, so wait.
                if not match or match.end() >= len(self.raw):
                    break

                self._show(self.raw[self.shown:match.end()])

                self._speak_early(match.start())

                self.shown = match.end()

    def finish(self):
        """Write whatever is left, end the line, wait for early speech."""

        with self.lock:

            tail = self.raw[self.shown:]

            if tail.strip():
                self._show(tail)

            self.shown = len(self.raw)

            if self.displayed:
                self.write("\n")

        if self.thread:
            self.thread.join()

    # ------------------------------------------------------
    # SCREEN
    # ------------------------------------------------------

    def _show(self, text):

        core = text.rstrip()
        separator = text[len(core):]

        shown = self.refine(core.strip())

        if not shown or not shown.strip():
            return

        if not self.displayed:

            # Wipe the "Thinking" animation before writing the reply.
            clear_status()

            self.write("\nNEXUS: ")

            self.displayed = True

        self.write(shown + separator)

    # ------------------------------------------------------
    # EARLY SPEECH
    # ------------------------------------------------------

    def _speak_early(self, sentence_end):
        """Speak the first sentence (raw[shown:sentence_end]) right away."""

        if self.thread or not self.displayed:
            return

        spoken = self.refine(self.raw[self.shown:sentence_end].strip()).strip()

        if len(spoken.split()) < MIN_EARLY_WORDS:
            return

        self.spoken_raw = self.raw[:sentence_end]

        self.thread = threading.Thread(
            target=self._say,
            args=(spoken,),
            daemon=True
        )

        self.thread.start()

    def _say(self, text):

        try:
            self.speaker.speak(text, quiet=True)
        except Exception as error:
            logger.error("Early speech failed: %s", error)

    def unspoken(self):
        """The raw text that early speech did not cover."""

        return self.raw[len(self.spoken_raw):].strip()

    @property
    def spoke_early(self):

        return bool(self.spoken_raw)
