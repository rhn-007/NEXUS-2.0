"""
NEXUS Follow-ups

Remembers, for a few minutes, which feature the last answer came from so a
short follow-up can be read against it: "and the battery?", "is that bad?",
"anything else?", "a bit louder", "start another one".

This only recognises short, whole-sentence follow-ups. Anything longer or
about something new is left for the normal paths and the model.
"""

import re
import time

from tools.media import detect_media, command_for
from tools.meet import mentions_meeting
from tools.system_info import detect_topics

# How long a follow-up still counts as being about the last answer.
EXPIRES_AFTER_SECONDS = 180

MAX_WORDS = 9

PC_TOPICS = (
    "summary", "usage", "apps", "battery", "cpu", "memory", "disk",
    "uptime", "network", "pc"
)

# "Anything else?" walks through these, skipping what was already said.
PC_CHAIN = (
    "summary", "usage", "disk", "battery", "cpu", "memory", "uptime",
    "network"
)

# The summary screen already shows these.
_COVERS = {
    "summary": {"summary", "cpu", "memory", "battery", "disk", "uptime"},
    "usage": {"usage", "apps"},
}

MEDIA_HELP = (
    "I can play or pause, skip to the next or previous track, mute, or "
    "change the volume. Just tell me what you'd like."
)

MEETING_HELP = (
    "I can start a new Google Meet, or join one if you give me the code."
)


_LEADING = re.compile(r"^(?:(?:hey |ok |okay |so |and |also |nexus[, ]+)+)")
_TRAILING = re.compile(r"(?:[, ]+(?:nexus|please))+$")

_ANYTHING_ELSE = re.compile(
    r"^(?:is there |was there |do you have |got )?(?:anything|something|what) else"
    r"(?: (?:to know|i should know|i need to know|that i should know|"
    r"do i need to know|should i know|for me|"
    r"about (?:it|that|this|the pc|my pc|my computer|the laptop|my laptop)))?$"
)

_MORE = re.compile(
    r"^(?:tell me more|more details?|more info(?:rmation)?|go on|elaborate|"
    r"details|show me more|what more|anything more)$"
)

_EXPLAIN = re.compile(
    r"^(?:is (?:that|it|this) (?:bad|ok|okay|fine|normal|good|a problem|serious)|"
    r"why|why is that|why is it|should i (?:worry|be worried)|"
    r"what does (?:that|it) mean|how bad is (?:that|it)|is that a problem)$"
)

_USAGE = re.compile(
    r"^(?:(?:which|what)(?: one| app| program| apps| programs)?(?: is| are)? "
    r"(?:using|taking|eating)(?: up)?(?: the)? most(?: memory| ram)?|"
    r"what(?:'s| is) using(?: up)?(?: the)? most(?: memory| ram)?)$"
)

_PC_TOPIC = re.compile(
    r"^(?:what about |how about |what of |what's the |how's the )?"
    r"(?:the |my )?(?P<word>battery|cpu|processor|memory|ram|disk|drive|"
    r"storage|space|network|wifi|wi-fi|uptime|[a-z] (?:drive|disk)|apps|"
    r"programs|specs)(?: (?:now|usage|level|status|space))?$"
)

_PC_WORDS = {
    "battery": "battery", "cpu": "cpu", "processor": "cpu",
    "memory": "memory", "ram": "memory", "disk": "disk", "drive": "disk",
    "storage": "disk", "space": "disk", "network": "network",
    "wifi": "network", "wi-fi": "network", "uptime": "uptime",
    "apps": "usage", "programs": "usage", "specs": "pc",
}

_VOLUME_UP = re.compile(
    r"^(?:(?:(?:increase|raise) (?:the )?volume|"
    r"turn (?:the )?volume up|(?:increase|raise) it) )?"
    r"(?:(?:a bit|a little|even|much) )?"
    r"(?:more|louder|higher|up|increase it|raise it)(?: still)?$"
)

# Accept common comparative phrases, including "a little bit more".
_VOLUME_MORE = re.compile(
    r"^(?:(?:a bit|a little(?: bit)?|even|much) )?more(?: still)?$"
)

_VOLUME_DOWN = re.compile(
    r"^(?:(?:(?:decrease|reduce|lower) (?:the )?volume|"
    r"turn (?:the )?volume down|(?:lower|decrease|reduce) it) )?"
    r"(?:(?:a bit|a little|even|much) )?"
    r"(?:lower|quieter|softer|down|less|lower it(?: more| again)?|decrease it|reduce it)(?: still)?$"
)

_NEXT = re.compile(
    r"^(?:what about )?(?:the )?(?:next|another)(?: one| song| track)?$"
)

_PREVIOUS = re.compile(
    r"^(?:the )?(?:previous|last|one before)(?: one| song| track)?$"
)

_AGAIN = re.compile(
    r"^(?:again|do it again|one more time|once more|repeat that)$"
)

_ANOTHER_MEETING = re.compile(
    r"^(?:start |make |open |create )?(?:another|a new|one more)"
    r"(?: one| meeting)?$"
)


def _clean(text):

    lowered = str(text or "").lower().replace("’", "'")
    lowered = re.sub(r"\s+", " ", lowered).strip(" .!?,")

    lowered = _LEADING.sub("", lowered).strip(" .!?,")
    lowered = _TRAILING.sub("", lowered).strip(" .!?,")

    return lowered


class FollowUps:

    def __init__(self, clock=time.monotonic):

        self.clock = clock
        self.state = None

    # ======================================================
    # WHAT WAS LAST ANSWERED
    # ======================================================

    def clear(self):

        self.state = None

    def active(self):

        if not self.state:
            return None

        if self.clock() - self.state["at"] > EXPIRES_AFTER_SECONDS:

            self.state = None

            return None

        return self.state

    def note(self, feature, topic="", command=""):

        state = self.active()

        if not state or state["feature"] != feature:

            state = {"feature": feature, "covered": set()}

        state["topic"] = topic
        state["command"] = command
        state["at"] = self.clock()

        if feature == "pc":
            state["covered"] |= _COVERS.get(topic, {topic})

        self.state = state

    def note_text(self, text):
        """Learn what a sentence was about when only its words are known."""

        topics = [t for t, _ in detect_topics(text) if t in PC_TOPICS]

        if topics:

            for topic in topics:
                self.note("pc", topic, f"system info {topic}")

            return

        media = detect_media(text)

        if media:

            action, value = media[-1]

            self.note("media", action, command_for(action, value))

            return

        if mentions_meeting(text):
            self.note("meeting", "meeting", "start meeting")

    def note_step(self, step):

        if step.action == "system_info":

            topic = step.value.split(" ")[0]

            if topic in PC_TOPICS:
                self.note("pc", topic, step.command)

        elif step.action == "media":

            value = step.value or ""

            topic = "set_volume" if value.startswith("volume ") else value

            self.note("media", topic, step.command)

        elif step.action in ("start_meeting", "join_meeting"):

            self.note("meeting", step.action, "start meeting")

    # ======================================================
    # CONTEXTUAL REFERENCE RESOLUTION
    # ======================================================

    _REFERENCE_REQUEST = re.compile(
        r"\b(?:search|look up|find|open|play|show|tell me about|"
        r"get|check|compare|summarize|research)\b",
        re.IGNORECASE
    )

    _PRONOUNS = re.compile(
        r"\b(?:him|her|them|it|his|hers|their|its)\b",
        re.IGNORECASE
    )

    _GENERIC_SUBJECTS = {
        "nexus", "you", "your", "i", "we", "they", "he", "she",
        "spotify", "youtube", "google", "apple", "the", "this", "that"
    }

    @staticmethod
    def _recent_subject(recent):
        """Find a named subject explicitly mentioned in the recent dialogue."""

        if not isinstance(recent, (list, tuple)):
            return None

        for message in reversed(recent):
            if not isinstance(message, dict):
                continue
            if str(message.get("role", "")).lower() != "assistant":
                continue

            content = str(message.get("content", "")).strip()
            if not content:
                continue

            candidates = re.findall(
                r"\b[A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){0,3}\b",
                content
            )
            for candidate in reversed(candidates):
                words = candidate.split()
                if not words or any(
                    word.strip(".,!?").casefold() in FollowUps._GENERIC_SUBJECTS
                    for word in words
                ):
                    continue
                if candidate.casefold() in {
                    "your", "you", "the", "i", "we", "yes", "no",
                    "sure", "okay", "here", "from", "and", "but"
                }:
                    continue
                return candidate.strip(".,!?")
        return None

    def resolve_reference(self, text, recent=None):
        """
        Resolve a short pronoun-based command against recent assistant context.
        Ambiguous messages are returned unchanged.
        """

        original = str(text or "").strip()
        if not original or not self._REFERENCE_REQUEST.search(original):
            return original
        if not self._PRONOUNS.search(original):
            return original

        subject = self._recent_subject(recent)
        if not subject:
            return original

        resolved = re.sub(r"\bhim\b", subject, original, flags=re.IGNORECASE)
        resolved = re.sub(r"\bher\b", subject, resolved, flags=re.IGNORECASE)
        resolved = re.sub(r"\bthem\b", subject, resolved, flags=re.IGNORECASE)
        resolved = re.sub(r"\bit\b", subject, resolved, flags=re.IGNORECASE)
        resolved = re.sub(r"\bhis\b", subject + "'s", resolved, flags=re.IGNORECASE)
        resolved = re.sub(r"\bhers\b", subject + "'s", resolved, flags=re.IGNORECASE)
        resolved = re.sub(r"\btheir\b", subject + "'s", resolved, flags=re.IGNORECASE)
        resolved = re.sub(r"\bits\b", subject + "'s", resolved, flags=re.IGNORECASE)
        # Remove the natural-language particle in phrases such as
        # "look him up on Spotify" before the existing site-search parser.
        resolved = re.sub(
            r"\bup\s+(on|in)\s+(spotify|youtube|github|wikipedia|reddit)\b",
            r"\1 \2",
            resolved,
            flags=re.IGNORECASE
        )
        return resolved


    # ======================================================
    # MATCHING
    # ======================================================

    def match(self, text):
        """
        (kind, value) when the text is a follow-up to the last answer,
        otherwise None. kinds: else, topic, explain, media, again, meeting.
        """

        state = self.active()

        if not state:
            return None

        cleaned = _clean(text)

        if not cleaned or len(cleaned.split()) > MAX_WORDS:
            return None

        if _ANYTHING_ELSE.match(cleaned) or _MORE.match(cleaned):
            return "else", None

        feature = state["feature"]

        if feature == "pc":

            if _EXPLAIN.match(cleaned):
                return "explain", None

            if _USAGE.match(cleaned):
                return "topic", "usage"

            found = _PC_TOPIC.match(cleaned)

            if found:

                word = found.group("word")

                if word.endswith(" drive") or word.endswith(" disk"):
                    return "topic", "disk"

                return "topic", _PC_WORDS[word]

            return None

        if feature == "media":

            if _AGAIN.match(cleaned):
                return "again", None

            if _NEXT.match(cleaned):
                return "media", "next"

            if _PREVIOUS.match(cleaned):
                return "media", "previous"

            if state["topic"] in ("volume_up", "volume_down", "set_volume"):

                # Relative "more" means continue the most recent adjustment,
                # not always increase the volume. The remembered action is
                # refreshed after each successful follow-up command.
                if (
                    state["topic"] in ("volume_up", "volume_down")
                    and _VOLUME_MORE.match(cleaned)
                ):
                    return "media", state["topic"]

                if _VOLUME_UP.match(cleaned):
                    return "media", "volume_up"

                if _VOLUME_DOWN.match(cleaned):
                    return "media", "volume_down"

            return None

        if feature == "meeting":

            if _ANOTHER_MEETING.match(cleaned) or _AGAIN.match(cleaned):
                return "meeting", None

        return None

    def next_pc_topic(self):
        """The next PC topic not yet said, or None when all were."""

        state = self.active()

        if not state or state["feature"] != "pc":
            return None

        for topic in PC_CHAIN:

            if topic not in state["covered"]:
                return topic

        return None
