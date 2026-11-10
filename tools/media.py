"""
NEXUS Media Tool

Controls whatever is playing by sending the same media keys a keyboard has:
play/pause, next, previous, volume up, volume down and mute. Only these
fixed keys are ever sent, never text or any other key.

Play/pause and mute are toggles: Windows does not say whether music is
playing, so NEXUS reports which key it pressed rather than claiming a state.
"""

import ctypes
import logging
import re
import sys
import time

from tools.base import BaseTool
from tools.response import ToolResponse


logger = logging.getLogger(__name__)


# Windows virtual-key codes for the media keys.
KEY_CODES = {
    "mute": 0xAD,
    "volume_down": 0xAE,
    "volume_up": 0xAF,
    "next": 0xB0,
    "previous": 0xB1,
    "play_pause": 0xB3
}

SIMPLE_ACTIONS = (
    "play_pause", "next", "previous", "volume_up", "volume_down", "mute"
)

# One key press moves the Windows volume by about 2%.
PERCENT_PER_PRESS = 2
PRESSES_FOR_A_NUDGE = 5
MAX_PRESSES = 60


# ==========================================================
# RECOGNISING REQUESTS
# ==========================================================

_THE = r"(?:the |this |that |my |some |current |a )*"

_MEDIA_OBJECT = (
    r"(?:music|songs?|tracks?|playback|audio|video|podcast|spotify|"
    r"playlist|youtube)"
)

_PATTERNS = [
    ("play_pause",
     rf"\b(?:pause|resume|unpause|stop|continue)\b {_THE}{_MEDIA_OBJECT}\b"),
    ("play_pause",
     rf"\bplay\b {_THE}{_MEDIA_OBJECT}\b(?: again)?"
     r"(?: (?:on|in|with) (?:spotify|youtube|opera|the pc|my pc))?$"),
    ("next",
     r"\b(?:next|skip)(?: to)?(?: the| this| that| current)?"
     r"(?: next)? (?:songs?|tracks?)\b"),
    ("previous", r"\bprevious (?:song|track)\b"),
    ("previous", r"\bgo back (?:a |one )?(?:song|track)\b"),
    ("previous", r"\b(?:play|go to|go back to|replay) the last (?:song|track)\b"),
    ("volume_up", r"\bvolume (?:up|higher)\b"),
    ("volume_up", r"\bturn (?:it |the (?:music|volume|sound|audio) )?up\b"),
    ("volume_up", r"\bturn up the (?:volume|music|sound|audio)\b"),
    ("volume_up", r"\b(?:increase|raise) the (?:volume|sound)\b"),
    ("volume_up", r"\bmake (?:it|the (?:music|sound|volume)) (?:louder|higher)\b"),
    ("volume_up", r"\b(?:a bit|a little|much|even) louder\b"),
    ("volume_down", r"\bvolume (?:down|lower)\b"),
    ("volume_down", r"\bturn (?:it |the (?:music|volume|sound|audio) )?down\b"),
    ("volume_down", r"\bturn down the (?:volume|music|sound|audio)\b"),
    ("volume_down", r"\b(?:decrease|lower|reduce) the (?:volume|sound)\b"),
    ("volume_down", r"\bmake (?:it|the (?:music|sound|volume)) (?:quieter|lower|softer)\b"),
    ("volume_down", r"\b(?:a bit|a little|much|even) (?:quieter|softer)\b"),
    ("mute",
     r"\b(?:mute|unmute) (?:the |my |this )*"
     r"(?:volume|sound|audio|music|pc|computer|laptop|speakers|everything)\b"),
    ("mute", r"\bturn (?:the )?(?:sound|volume|music|audio) off\b"),
]

_COMPILED = [(action, re.compile(pattern)) for action, pattern in _PATTERNS]

_SET_VOLUME = [
    re.compile(
        r"\b(?:set|put|change|make) (?:the )?(?:volume|sound|music)"
        r"(?: level)? (?:to|at) (\d{1,3})(?: ?%| ?percent)?(?!\d)"
    ),
    re.compile(r"\bvolume (?:to|at) (\d{1,3})(?: ?%| ?percent)?(?!\d)"),
    re.compile(r"\b(\d{1,3})(?: ?%| ?percent) volume\b"),
]

_TYPED = re.compile(
    r"^media (?:(?P<action>play_pause|next|previous|volume_up|volume_down|"
    r"mute)|volume (?P<level>\d{1,3}))$"
)

_QUESTION_START = re.compile(
    r"^(?:what|which|who|when|where|why|how|whose)\b"
)

_TRAILING = re.compile(
    r"\s+(?:please|for me|thanks|thank you|right now|now)$"
)

_CLAUSE_SPLIT = re.compile(r"\s*(?:;|,|\band\b|\bthen\b)\s*")

_MENTIONS_MEDIA = re.compile(
    r"\b(?:music|songs?|tracks?|volume|sound|audio|spotify|youtube|video|"
    r"playback|podcast|playlist|mute|unmute|louder|quieter|skip|pause|"
    r"resume|next|previous|turn it up|turn it down)\b"
)


_VOLUME_OF = re.compile(r"\bvolume of\b")


def mentions_media(text):
    """True when the text talks about music, sound or playback at all."""

    lowered = str(text or "").lower()

    # "the volume of a sphere" is maths, not the speaker volume.
    if _VOLUME_OF.search(lowered):
        return False

    return bool(_MENTIONS_MEDIA.search(lowered))


# What the message must contain for a planner-chosen action to be believed.
_EVIDENCE = {
    "play_pause": r"\b(?:play|pause|resume|stop|continue|unpause)\b",
    "next": r"\b(?:next|skip)\b",
    "previous": r"\b(?:previous|last|back)\b",
    "volume_up": r"\b(?:up|louder|higher|increase|raise|loud)\b",
    "volume_down": r"\b(?:down|quieter|lower|softer|decrease|reduce|quiet)\b",
    "mute": r"\b(?:mute|unmute|silence|off)\b",
    "set_volume": r"\d",
}


def media_choice_fits(text, choice):
    """
    Does the message back up this media action? A small model can pick one
    from a stray word, so the message itself has to point at it.
    """

    lowered = str(text or "").lower()

    key = "set_volume" if choice.startswith("volume ") else choice

    pattern = _EVIDENCE.get(key)

    return bool(pattern and re.search(pattern, lowered))


def _normal(text):

    lowered = str(text or "").lower().replace("’", "'")

    return re.sub(r"\s+", " ", lowered).strip(" .!?,")


def _level(raw):

    return str(min(100, int(raw)))


def _action_for_clause(clause):

    clause = clause.strip(" .!?,")

    while _TRAILING.search(clause):
        clause = _TRAILING.sub("", clause)

    # Questions about music are not commands ("what's the next song?").
    if _QUESTION_START.match(clause):
        return None

    for pattern in _SET_VOLUME:

        match = pattern.search(clause)

        if match:
            return "set_volume", _level(match.group(1))

    for action, pattern in _COMPILED:

        if pattern.search(clause):
            return action, ""

    return None


def detect_media(text):
    """
    Media commands in a sentence, in order, as (action, value) pairs.
    value is only used by set_volume (a level from 0 to 100).
    """

    lowered = _normal(text)

    typed = _TYPED.match(lowered)

    if typed:

        if typed.group("action"):
            return [(typed.group("action"), "")]

        return [("set_volume", _level(typed.group("level")))]

    found = []

    for clause in _CLAUSE_SPLIT.split(lowered):

        result = _action_for_clause(clause)

        if result and result not in found:
            found.append(result)

    return found


def command_for(action, value=""):

    if action == "set_volume":
        return f"media volume {value}"

    return f"media {action}"


# ==========================================================
# SENDING KEYS
# ==========================================================

class MediaUnavailable(Exception):
    pass


class KeySender:
    """Presses media keys on Windows."""

    KEYEVENTF_EXTENDEDKEY = 0x1
    KEYEVENTF_KEYUP = 0x2

    def press(self, key_code, count=1):

        windll = getattr(ctypes, "windll", None)

        if sys.platform != "win32" or windll is None:
            raise MediaUnavailable("Media keys only work on Windows.")

        for _ in range(count):

            windll.user32.keybd_event(
                key_code, 0, self.KEYEVENTF_EXTENDEDKEY, 0
            )
            windll.user32.keybd_event(
                key_code,
                0,
                self.KEYEVENTF_EXTENDEDKEY | self.KEYEVENTF_KEYUP,
                0
            )

            if count > 1:
                time.sleep(0.008)


# ==========================================================
# THE TOOL
# ==========================================================

class MediaTool(BaseTool):

    name = "media"

    description = (
        "Plays, pauses and skips media and changes the volume by sending "
        "media keys."
    )

    def __init__(self, sender=None):

        self.sender = sender or KeySender()

    def can_handle(self, query):

        return bool(query) and bool(detect_media(query))

    def execute(self, query):

        actions = detect_media(query)

        if not actions:

            return ToolResponse.failure(
                "I'm not sure what you'd like me to do with the media."
            )

        messages = []

        try:

            for action, value in actions:
                messages.append(self.perform(action, value))

        except MediaUnavailable as error:

            return ToolResponse.failure(str(error))

        except Exception as error:

            logger.warning("Media control failed: %s", error)

            return ToolResponse.failure(
                "I couldn't send that media key."
            )

        return ToolResponse.success(" ".join(messages))

    def perform(self, action, value=""):

        sender = self.sender

        if action == "play_pause":
            sender.press(KEY_CODES["play_pause"])
            return "Pressed play/pause."

        if action == "next":
            sender.press(KEY_CODES["next"])
            return "Next track."

        if action == "previous":
            sender.press(KEY_CODES["previous"])
            return "Previous track."

        if action == "volume_up":
            sender.press(KEY_CODES["volume_up"], PRESSES_FOR_A_NUDGE)
            return "Volume up."

        if action == "volume_down":
            sender.press(KEY_CODES["volume_down"], PRESSES_FOR_A_NUDGE)
            return "Volume down."

        if action == "mute":
            sender.press(KEY_CODES["mute"])
            return "Pressed mute. It toggles, so say it again to undo."

        if action == "set_volume":

            level = max(0, min(100, int(value)))

            # Go to silence first, then up to the level.
            sender.press(KEY_CODES["volume_down"], MAX_PRESSES)

            ups = round(level / PERCENT_PER_PRESS)

            if ups:
                sender.press(KEY_CODES["volume_up"], min(ups, MAX_PRESSES))

            return f"Volume set to about {level}%."

        raise ValueError(f"Unknown media action: {action}")
