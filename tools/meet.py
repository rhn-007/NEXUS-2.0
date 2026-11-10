"""
NEXUS Google Meet Tool

Opens a Google Meet from a spoken or typed meeting code. Only
meet.google.com links are ever built, and only from a code that passes a
strict check. Joining is left to the person: the Meet page asks for the
final "Join now" click.
"""

import logging
import re

from tools.base import BaseTool
from tools.response import ToolResponse


logger = logging.getLogger(__name__)


# Meet codes are ten letters written 3-4-3, for example abc-defg-hij.
_DASHED_CODE = re.compile(r"(?<![a-z])([a-z]{3})-([a-z]{4})-([a-z]{3})(?![a-z])")

_JOIN = re.compile(
    r"\b(?:join|joining|get me (?:into|in)|hop (?:on|into)|"
    r"jump (?:on|into|in))\b"
)

_MEETING_WORD = re.compile(r"\b(?:meet|meeting|call|google meet)\b")

NATO_LETTERS = {
    "alpha": "a", "alfa": "a", "bravo": "b", "charlie": "c", "delta": "d",
    "echo": "e", "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i",
    "juliet": "j", "juliett": "j", "kilo": "k", "lima": "l", "mike": "m",
    "november": "n", "oscar": "o", "papa": "p", "quebec": "q", "romeo": "r",
    "sierra": "s", "tango": "t", "uniform": "u", "victor": "v",
    "whiskey": "w", "xray": "x", "yankee": "y", "zulu": "z"
}

# How letter names are often transcribed. Used only when the plain reading
# does not give exactly ten letters.
LETTER_NAME_WORDS = {
    "bee": "b", "see": "c", "sea": "c", "dee": "d", "gee": "g", "jay": "j",
    "kay": "k", "ell": "l", "em": "m", "en": "n", "oh": "o", "pee": "p",
    "cue": "q", "are": "r", "ess": "s", "tee": "t", "you": "u", "ex": "x",
    "why": "y", "zee": "z", "zed": "z", "eye": "i"
}

# Words that lead up to the code. The code is whatever follows the last one.
_LEAD_IN = {
    "join", "joining", "into", "in", "on", "to", "meeting", "meet", "call",
    "code", "code's", "id", "is", "its", "it's", "session", "link", "number"
}

_LEADING_FILLER = {
    "my", "the", "with", "here", "please", "hello", "this", "that's",
    "thats"
}

_TRAILING_FILLER = {"please", "thanks", "thank", "now"}


def wants_meeting(text):
    """True when the sentence asks to join a meeting or call."""

    lowered = str(text or "").lower()

    return bool(_JOIN.search(lowered) and _MEETING_WORD.search(lowered))


_MENTIONS_MEETING = re.compile(
    r"\b(?:meeting|meet|google meet|video call|conference call)\b"
)


def mentions_meeting(text):
    """True when the text talks about a meeting, whatever else it says."""

    return bool(_MENTIONS_MEETING.search(str(text or "").lower()))


def _letters(tokens, use_letter_names):

    letters = []

    for token in tokens:

        if token in NATO_LETTERS:
            letters.append(NATO_LETTERS[token])

        elif use_letter_names and token in LETTER_NAME_WORDS:
            letters.append(LETTER_NAME_WORDS[token])

        elif token.isalpha():
            letters.extend(token)

        else:
            return None

    return letters


def code_tokens(text):
    """The words that could make up a spoken code, after the lead-in."""

    lowered = str(text or "").lower().replace("’", "'")
    lowered = re.sub(r"\bx[\s-]?ray\b", "xray", lowered)

    # "abc dash defg dash hij": the spoken separators are not letters.
    tokens = [
        token for token in re.findall(r"[a-z']+", lowered)
        if token not in ("dash", "hyphen", "minus")
    ]

    last_lead_in = -1

    for index, token in enumerate(tokens):

        if token in _LEAD_IN:
            last_lead_in = index

    tokens = tokens[last_lead_in + 1:]

    while tokens and tokens[0] in _LEADING_FILLER:
        tokens = tokens[1:]

    while tokens and tokens[-1] in _TRAILING_FILLER:
        tokens = tokens[:-1]

    return tokens


def parse_meet_code(text):
    """
    Read a meeting code from typed or spoken text.

    Accepts abc-defg-hij, "abc defg hij", abcdefghij, letters said one by
    one, and NATO words. Returns the code as 'abc-defg-hij', or None when
    the text does not give exactly ten letters.
    """

    lowered = str(text or "").lower()

    dashed = _DASHED_CODE.search(lowered)

    if dashed:
        return "-".join(dashed.groups())

    tokens = code_tokens(lowered)

    if not tokens:
        return None

    for use_letter_names in (False, True):

        letters = _letters(tokens, use_letter_names)

        if letters is not None and len(letters) == 10:

            joined = "".join(letters)

            return f"{joined[:3]}-{joined[3:7]}-{joined[7:]}"

    return None


def looks_like_code_attempt(text):
    """
    After NEXUS asked for the code: does this look like a garbled code
    (worth asking again) rather than something unrelated?
    """

    tokens = code_tokens(text)

    if not tokens or not all(token.isalpha() for token in tokens):
        return False

    spelled = sum(
        1 for token in tokens
        if len(token) == 1
        or token in NATO_LETTERS
        or token in LETTER_NAME_WORDS
    )

    if spelled >= 5:
        return True

    if len(tokens) == 3:

        first, middle, last = (len(token) for token in tokens)

        return 2 <= first <= 4 and 3 <= middle <= 5 and 2 <= last <= 4

    return False


class MeetTool(BaseTool):

    name = "meet"

    description = "Opens a Google Meet from a meeting code."

    def __init__(self, browser):

        self.browser = browser

    def can_handle(self, query):

        return bool(
            query
            and wants_meeting(query)
            and parse_meet_code(query)
        )

    def execute(self, query):

        code = parse_meet_code(query)

        if not code:

            return ToolResponse.failure(
                "What's the meeting code?"
            )

        if self.browser is None:

            return ToolResponse.failure(
                "I couldn't find the browser tool."
            )

        # The code itself is deliberately not logged.
        logger.info("Opening a Google Meet link.")

        result = self.browser.open_opera(
            f"https://meet.google.com/{code}"
        )

        if not result.success:
            return result

        return ToolResponse.success(
            f"Opening Meet {code}. Press Join now when the page loads."
        )
