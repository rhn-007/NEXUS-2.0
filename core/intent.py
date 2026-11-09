"""
NEXUS Intent Fast Path

Turns natural sentences such as "ok, now can u reseach about xyz" into the
exact commands NEXUS tools already understand. It uses no model, so it is
instant. Anything it is not sure about is left alone and falls through to
the planner or to normal conversation.
"""

import difflib
import re
from urllib.parse import quote_plus
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """One thing to do. `command` is the text handed to the tool router."""

    action: str
    value: str = ""
    command: str = ""
    # Run before the tool router, which would read the same sentence
    # differently (for example as a Google search).
    first: bool = False


# Actions that NEXUS performs itself rather than through the tool router.
BUILTIN_ACTIONS = (
    "show_speech_profile",
    "forget_speech_profile",
    "performance_report",
    "about_me",
    "switch_mode"
)

# Sites that can be searched directly instead of through Google.
SITE_SEARCH_URLS = {
    "youtube": "https://www.youtube.com/results?search_query={}",
    "github": "https://github.com/search?q={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
    "reddit": "https://www.reddit.com/search/?q={}"
}

# Wording the existing assistant checks already recognise.
BUILTIN_COMMANDS = {
    "show_speech_profile": "show my speech profile",
    "forget_speech_profile": "forget my speech profile",
    "performance_report": "show performance report",
    "about_me": "what do you know about me"
}


# ==========================================================
# CLEANING
# ==========================================================

_LEADING_FILLERS = [
    r"(?:ok|okay|alright|all right|right|so|well|hey|hi|hello|yo|now|"
    r"then|also|and|please|nexus|jarvis)\b",
    r"(?:can|could|would|will)\s+(?:you|u|ya)\b(?:\s+please)?",
    r"(?:i|we)\s+(?:want|need|would like|wanna)\s+(?:you\s+|u\s+)?to\b",
    r"i'd like\s+(?:you\s+|u\s+)?to\b",
    r"(?:go ahead and|help me|let's|lets|do me a favou?r and|"
    r"i was wondering if you could)\b",
    r"(?:just|quickly)\b"
]

_TRAILING_FILLERS = re.compile(
    r"[\s,.:;!?]*\b(?:please|for me|thanks|thank you|right now|now|"
    r"if you can)\s*$"
)

_SEPARATORS = r"[\s,.:;!\-]*"


def clean(text):
    """Lowercase, tidy punctuation and spacing."""

    text = str(text or "").lower().replace("’", "'")
    text = re.sub(r"[“”\"]", "", text)
    text = re.sub(r"\s+", " ", text)

    # A space typed in the wrong place: "an dsearch" -> "and search".
    text = re.sub(r"\ban d(?=[a-z])", "and ", text)
    text = re.sub(r"\badn\b", "and", text)

    return text.strip(" .,!?;:")


def strip_fillers(text):
    """Remove politeness and lead-in words from both ends."""

    text = clean(text)

    changed = True

    while changed and text:

        changed = False

        for pattern in _LEADING_FILLERS:

            match = re.match(r"\s*" + pattern + _SEPARATORS, text)

            if match and match.end() > 0:

                text = text[match.end():]
                changed = True

        trailing = _TRAILING_FILLERS.search(text)

        if trailing and trailing.start() > 0:

            text = text[:trailing.start()]
            changed = True

    return text.strip(" .,!?;:")


# ==========================================================
# VERBS
# ==========================================================

_VERB_PHRASES = [
    ("research", [
        "research", "investigate", "look into", "find out about",
        "learn about", "find information about", "find info about",
        "find information on", "find info on", "dig into", "read up on"
    ]),
    ("search", [
        "search the web for", "search online for", "search the internet for",
        "search google for", "search for", "search", "google", "look up",
        "lookup"
    ]),
    ("open", [
        "open up", "open", "launch", "start up", "start", "run",
        "bring up", "pull up", "fire up"
    ]),
    ("go", [
        "go to", "visit", "navigate to", "browse to", "browse"
    ])
]

_PHRASES_LONGEST_FIRST = sorted(
    (
        (phrase, kind)
        for kind, phrases in _VERB_PHRASES
        for phrase in phrases
    ),
    key=lambda item: len(item[0]),
    reverse=True
)

_FIRST_WORDS = {
    phrase.split()[0]
    for phrase, _ in _PHRASES_LONGEST_FIRST
}

_TYPO_TARGETS = (
    "research", "investigate", "search", "google", "open", "launch",
    "visit", "browse", "navigate", "lookup"
)

_NEVER_CORRECT_SUFFIXES = ("ed", "ing", "es", "er", "ers", "s")

# Words that are not real targets: such a request is really a question
# about NEXUS ("can you search the web?"), not something to do.
GENERIC_TARGETS = {
    "it", "that", "this", "them", "those", "these", "him", "her",
    "the web", "web", "the internet", "internet", "online", "anything",
    "something", "stuff", "things", "me", "you", "for me", "the net",
    "google", "the web for me"
}

BROWSER_TARGETS = {
    "browser", "the browser", "a browser", "my browser", "web browser",
    "the web browser", "internet browser", "opera", "opera browser",
    "the opera browser", "internet"
}

_DOMAIN = re.compile(
    r"^(?:https?://)?"
    r"([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|ai|edu|gov|co|dev|app|me|tv|uk))"
    r"(/\S*)?$"
)

_URL = re.compile(r"^https?://\S+$")


def _correct_first_word(text):
    """Repair a mistyped action word, e.g. 'reseach' -> 'research'."""

    words = text.split()

    if not words:
        return text

    first = words[0]

    if first in _FIRST_WORDS or len(first) < 4:
        return text

    if first.endswith(_NEVER_CORRECT_SUFFIXES):
        return text

    best = None

    for candidate in _TYPO_TARGETS:

        if abs(len(candidate) - len(first)) > 1:
            continue

        same_letters = (
            len(first) == len(candidate)
            and sorted(first) == sorted(candidate)
            and first[0] == candidate[0]
        )

        ratio = difflib.SequenceMatcher(None, first, candidate).ratio()

        if same_letters or ratio >= 0.8:

            best = candidate
            break

    if best is None:
        return text

    return " ".join([best] + words[1:])


def _match_verb(text):
    """Return (kind, target) when the text starts with an action phrase."""

    text = _correct_first_word(text)

    for phrase, kind in _PHRASES_LONGEST_FIRST:

        if text == phrase:
            return kind, ""

        if text.startswith(phrase + " "):
            return kind, text[len(phrase) + 1:].strip()

    return None, ""


def has_phrase(text, phrase):

    return re.search(
        r"(?<![\w])" + re.escape(phrase) + r"(?![\w])",
        text
    ) is not None


# ==========================================================
# NATURAL MATH
# ==========================================================

_MATH_LEAD = re.compile(
    r"^(?:what is|what's|whats|how much is|calculate|compute|solve|"
    r"work out)\s+(.+)$"
)

_NUMBER = r"\d+(?:\.\d+)?"


def natural_math_expression(text):
    """'what's 12 times 7' -> '12 * 7', or None when it is not arithmetic."""

    match = _MATH_LEAD.match(text)

    if not match:
        return None

    expression = match.group(1)

    expression = re.sub(
        rf"({_NUMBER})\s*(?:%|percent|per cent)\s+of\s+({_NUMBER})",
        r"(\1/100*\2)",
        expression
    )

    for words, symbol in (
        (r"multiplied by|times|\bx\b", "*"),
        (r"divided by|over", "/"),
        (r"plus|and", "+"),
        (r"minus|take away|less", "-")
    ):
        expression = re.sub(rf"\s*(?:{words})\s*", f" {symbol} ", expression)

    expression = re.sub(r"\s+", " ", expression).strip()

    if not re.fullmatch(r"[\d\s+\-*/%().]+", expression):
        return None

    if not re.search(r"\d", expression):
        return None

    if not re.search(r"[+\-*/%]", expression):
        return None

    return expression


# ==========================================================
# BUILT-IN FEATURE PHRASES
# ==========================================================

_BUILTIN_PATTERNS = [
    (
        "forget_speech_profile",
        r"(?:forget|clear|delete|reset|erase|wipe)\s+(?:my|the)\s+"
        r"(?:personal\s+)?(?:speech|speaking)\s+profile"
    ),
    (
        "show_speech_profile",
        r"(?:what (?:have|did) you learn(?:ed|t)? about (?:how i speak|"
        r"my speak\w*|my speech)|(?:show|tell|give)(?: me)? "
        r"(?:my|the) (?:speech|speaking) profile|my (?:speech|speaking) "
        r"profile|speech profile|what do you know about my speaking style)"
    ),
    (
        "performance_report",
        r"(?:(?:show|give|let me see|tell|display)(?: me)?(?: the| your| my)?"
        r" (?:nexus )?(?:performance|self[- ]observation) "
        r"(?:report|summary|stats|statistics)|how (?:are|have) you "
        r"(?:been )?performing)"
    ),
    (
        "about_me",
        r"(?:what (?:do|did) (?:you|u) know about me|tell me (?:about me|"
        r"about myself|what you know about me)|who am i|"
        r"(?:show|what(?:'s| is) in) my profile)"
    )
]

_EXIT_PHRASES = {
    "exit nexus", "quit nexus", "close nexus", "shut down nexus",
    "shutdown nexus", "shut nexus down", "shut down", "exit", "quit",
    "shutdown"
}


# ==========================================================
# FAST PATH
# ==========================================================

_CHAT_VERBS_AFTER_MODAL = (
    "tell", "explain", "describe", "write", "summarize", "summarise",
    "give", "say", "teach", "remember", "think", "answer", "show me how",
    "what", "why", "how", "who"
)

_REQUEST_CUES = re.compile(
    r"\b(?:(?:can|could|would|will)\s+(?:you|u)|please|"
    r"i\s+(?:want|need|would like|wanna)\s+(?:you\s+|u\s+)?to|"
    r"i'd like|go ahead|help me)\b"
)

_TOOL_NOUNS = (
    "browser", "opera", "notepad", "spotify", "google", "youtube",
    "folder", "explorer", "whatsapp", "excel", "speech profile",
    "performance report", "continuous", "keyboard mode", "voice mode"
)


class IntentFastPath:

    def __init__(self, websites=None, app_targets=None):

        self.websites = sorted(
            {str(name).lower() for name in (websites or [])},
            key=len,
            reverse=True
        )

        self.app_targets = sorted(
            {str(name).lower() for name in (app_targets or [])},
            key=len,
            reverse=True
        )

    # ------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------

    def fast_steps(self, text):
        """Return the steps for a clear request, or [] when unsure."""

        cleaned = strip_fillers(text)

        if not cleaned:
            return []

        parts = self._split(cleaned)

        if len(parts) > 1:

            steps = self._parse_parts(parts)

            if steps:
                return steps

        step = self._parse_one(cleaned)

        return [step] if step else []

    def builtin_command(self, text):
        """Wording the assistant's own commands already understand."""

        cleaned = strip_fillers(text)

        for action, pattern in _BUILTIN_PATTERNS:

            if re.fullmatch(pattern, cleaned):
                return BUILTIN_COMMANDS[action]

        return None

    def is_exit_request(self, text):

        cleaned = strip_fillers(text)

        return cleaned in _EXIT_PHRASES and cleaned not in (
            "exit", "quit", "shutdown"
        )

    def looks_like_request(self, text):
        """Cheap check for whether a message is worth sending to the planner."""

        lowered = clean(text)

        if not lowered or len(lowered) > 300:
            return False

        cleaned = strip_fillers(text)

        if _REQUEST_CUES.search(lowered):

            if cleaned.startswith(_CHAT_VERBS_AFTER_MODAL):
                return False

            return True

        kind, _ = _match_verb(cleaned)

        if kind:
            return True

        return any(has_phrase(lowered, noun) for noun in _TOOL_NOUNS)

    # ------------------------------------------------------
    # PARSING
    # ------------------------------------------------------

    _SEPARATOR = re.compile(
        r"(\s*(?:;|,\s*(?:and\s+)?(?:then\s+)?|"
        r"\s+and\s+(?:then\s+|also\s+)?|\s+then\s+|"
        r"\s+after that\s+)\s*)"
    )

    def _split(self, cleaned):
        """
        Split a sentence into steps at 'and', 'then' and commas, but only
        where a new action begins. 'search for matrices and determinants'
        stays one search.
        """

        pieces = self._SEPARATOR.split(cleaned)

        parts = []

        for index in range(0, len(pieces), 2):

            text = pieces[index].strip()

            if not text:
                continue

            separator = pieces[index - 1] if index > 0 else ""

            if parts and not self._starts_new_step(text, parts[-1]):

                joiner = (
                    separator
                    if re.search(r"[a-z]", separator)
                    else separator.strip() + " "
                )

                parts[-1] += joiner + text

            else:

                parts.append(text)

        return parts

    def _starts_new_step(self, text, previous):

        text = strip_fillers(text)

        kind, _ = _match_verb(text)

        if kind:
            return True

        # "open notepad and calculator": a bare app after an open step.
        previous_kind, _ = _match_verb(strip_fillers(previous))

        if previous_kind in ("open", "go"):

            bare = re.sub(r"^(?:the|my|a|an)\s+", "", text)

            return (
                bare in self.app_targets
                or bare in self.websites
                or bare in BROWSER_TARGETS
            )

        return False

    def _parse_parts(self, parts):

        steps = []

        for part in parts:

            part = strip_fillers(part)

            step = self._parse_one(part)

            if step is None and steps and steps[-1].action in (
                "open_app", "open_website"
            ):
                # "open notepad and calculator": reuse the verb.
                step = self._parse_one("open " + part)

            if step is None:
                return []

            steps.append(step)

        if len(steps) < 2:
            return []

        return drop_redundant_steps(steps)

    def _parse_one(self, text):

        text = strip_fillers(text)

        expression = natural_math_expression(text)

        if expression:

            return Step(
                "calculate",
                expression,
                f"calculate {expression}"
            )

        kind, target = _match_verb(text)

        if not kind:
            return None

        target = self._clean_target(target)

        if not target or target in GENERIC_TARGETS:
            return None

        if kind == "research":

            if len(target) > 150:
                return None

            return Step("research", target, f"research {target}")

        if kind == "search":

            site_first = re.match(
                r"^(?:on\s+)?(youtube|github|wikipedia|reddit)\s+for\s+(.+)$",
                target
            )
            site_last = re.match(
                r"^(.+?)\s+(?:on|in)\s+(youtube|github|wikipedia|reddit)$",
                target
            )

            if site_first:
                return site_search_step(site_first.group(1), site_first.group(2))

            if site_last:
                return site_search_step(site_last.group(2), site_last.group(1))

            target = re.sub(
                r"\s+(?:on google|on the web|on the internet|online|"
                r"on opera)$",
                "",
                target
            ).strip()

            if not target or target in GENERIC_TARGETS or len(target) > 150:
                return None

            return Step("web_search", target, f"search {target}")

        return self._parse_open(kind, target)

    def _clean_target(self, target):

        target = clean(target)

        target = re.sub(r"^(?:about|on|into|for)\s+", "", target)

        return target.strip()

    def _parse_open(self, kind, target):

        target = re.sub(r"^(?:up\s+)?(?:the|my|a|an)\s+", "", target)
        target = re.sub(
            r"\s+(?:app|application|program|for me|please)$",
            "",
            target
        ).strip()

        if not target or target in GENERIC_TARGETS:
            return None

        if kind == "open" and (
            target in BROWSER_TARGETS
            or f"the {target}" in BROWSER_TARGETS
        ):
            return Step("open_browser", "", "open browser")

        for site in self.websites:

            if target == site or (
                kind == "go" and has_phrase(target, site)
            ):
                return Step("open_website", site, f"go to {site}")

        if _URL.match(target):
            return Step("open_website", target, f"go to {target}")

        domain = _DOMAIN.match(target)

        if domain:

            url = (
                target if target.startswith("http")
                else "https://" + target
            )

            return Step("open_website", url, f"go to {url}")

        if kind == "go":
            return None

        for alias in self.app_targets:

            if target == alias:
                return Step("open_app", alias, f"open {alias}")

        return None


def site_search_step(site, query):
    """Search a site directly, e.g. YouTube, instead of through Google."""

    url = SITE_SEARCH_URLS[site].format(quote_plus(query))

    return Step("open_website", url, f"go to {url}", first=True)


def drop_redundant_steps(steps):
    """Opening the browser is pointless before a search or a website."""

    merged = []

    for step in steps:

        previous = merged[-1] if merged else None

        # "open youtube" then "search for X" means search YouTube for X.
        if (
            step.action == "web_search"
            and previous is not None
            and previous.action == "open_website"
            and previous.value in SITE_SEARCH_URLS
        ):
            merged[-1] = site_search_step(previous.value, step.value)
            continue

        merged.append(step)

    if any(step.action in ("web_search", "open_website") for step in merged):

        return [step for step in merged if step.action != "open_browser"]

    return merged


def app_targets_from(application_tool):
    """Every app, folder and shortcut name the application tool can open."""

    names = set()

    if application_tool is None:
        return []

    for info in getattr(application_tool, "applications", {}).values():
        names.update(info.get("aliases", []))

    names.update(getattr(application_tool, "folders", {}))
    names.update(("file explorer", "explorer"))

    return sorted(names)
