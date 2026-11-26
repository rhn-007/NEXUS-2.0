"""Deterministic personal-memory question recognition and answers."""

import re


_FILLERS = re.compile(
    r"^(?:(?:hey|ok|okay|so|and|nexus|please|tell me|"
    r"(?:can you|could you|can u)\s+(?:please\s+)?tell me|"
    r"can you|could you|can u)[,\s]+)+"
)

_FACT_QUESTIONS = (
    re.compile(r"^(?:what(?:'s| is| are)|who(?:'s| is)) my (?P<favourite>favou?rite )?(?P<thing>.+)$"),
    re.compile(r"^what (?P<thing>[a-z ]{2,25}?) am i (?:currently |now )?(?:working on|building|doing)$"),
    re.compile(r"^(?:tell me|remind me of) my (?P<favourite>favou?rite )?(?P<thing>.+)$"),
    re.compile(r"^(?:do you (?:know|remember)|you know|you remember) my (?P<favourite>favou?rite )?(?P<thing>.+)$"),
)

_PREFERENCE_QUESTIONS = re.compile(
    r"^(?:what do i prefer|what are my preferences|what(?:'s| is) my preferred "
    r"(?:style|way|format)|what style do i prefer|how do i (?:like|want) "
    r"my (?:answers|explanations|replies|responses))$"
)

_TV_SHOW_QUESTIONS = re.compile(
    r"^(?:what tv shows have i told you i enjoy|"
    r"what tv shows have i mentioned|"
    r"which tv shows do i enjoy|"
    r"what tv shows do i enjoy|"
    r"what television shows have i told you i enjoy|"
    r"what shows have i told you i enjoy)$"
)

_INTEREST_QUESTIONS = re.compile(
    r"^(?:what (?:is my hobby|are my hobbies|are my interests|"
    r"are my hobbies and interests)|"
    r"what about my (?:hobbies|interests)|"
    r"about my (?:hobbies|interests)|"
    r"what (?:hobbies|interests) do i have|"
    r"what interests did i mention earlier|"
    r"what interests have i mentioned(?: earlier)?|"
    r"what do i like doing|"
    r"tell me about my (?:hobbies|interests)|"
    r"what do you know about my (?:hobbies|interests)|"
    r"what do you remember about my (?:hobbies|interests)|"
    r"what have i told you about my (?:hobbies|interests))$"
)

_TOPIC_ACTIVITY_QUESTION = re.compile(
    r"^what have i told you about my (?P<topics>[a-z ,and]+?) activities"
    r"(?: separate what you know from what you don'?t know)?$"
)


def _tv_show_identity(title):
    """Deduplicate show titles regardless of a leading article."""
    return re.sub(r"^(?:the|a|an)\s+", "", _norm(title))


def _norm(word):

    return re.sub(r"\s+", " ", str(word or "").lower().replace("_", " ")
                  .replace("colour", "color")).strip()


def _join(values):

    values = list(values)

    if len(values) <= 1:
        return "".join(values)

    return ", ".join(values[:-1]) + " and " + values[-1]

def _clean_interest_value(value):
    """Normalize legacy interest fragments for display without changing SQLite."""
    original = " ".join(str(value or "").split()).strip(" .,!?:;")
    if not original:
        return None

    cleaned = re.sub(
        r"\s+as (?:my |the )?favou?rite sport$",
        "",
        original,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(
        r"^(?:to\s+)?play(?:ing)?\s+",
        "",
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = re.sub(
        r"^(?:playing\s+)?(?:the\s+)?tv\s+show\s+",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip(" .,!?:;")

    tokens = re.findall(r"[a-z0-9]+", cleaned.lower())
    if not tokens:
        return None

    # These are incomplete conversational fragments, not interests.
    fragment_only = {
        "sometimes", "occasionally", "often", "usually", "rarely",
        "something", "anything", "everything", "stuff",
        "things", "whatever", "it", "this", "that", "them", "there"
    }
    if all(token in fragment_only for token in tokens):
        return None

    return cleaned or None


def _clean_tv_show_value(value):
    """Extract a TV-show title from explicit labels or legacy viewing phrases."""
    original = " ".join(str(value or "").split()).strip(" .,!?:;")
    if not original:
        return None

    match = re.match(
        r"^(?:(?:watching|playing|following|enjoying|liking)\s+)?"
        r"(?:the\s+)?(?:tv\s+show|television\s+series)\s+(.+)$",
        original,
        flags=re.IGNORECASE
    )
    if match:
        title = match.group(1).strip(" .,!?:;")
    else:
        viewing = re.match(
            r"^watching\s+(?:the\s+)?(.+)$",
            original,
            flags=re.IGNORECASE
        )
        if not viewing:
            return None
        title = viewing.group(1).strip(" .,!?:;")

    # Normalize a known legacy speech-recognition variant confirmed by the user.
    if _norm(title) in {"the met list", "met list"}:
        return "The Mentalist"
    return title.title() if title else None


def _clean_tv_show_title(value):
    """Clean a title already stored under the dedicated tv_show key."""
    title = " ".join(str(value or "").split()).strip(" .,!?:;") or None
    if title and _norm(title) in {"the met list", "met list"}:
        return "The Mentalist"
    return title.title() if title else None


def _matches_interest_retraction(existing_value, title):
    """Match a retracted title against current and legacy interest wording."""
    existing = _norm(existing_value)
    target = _norm(title)
    prefixes = (
        "watching the tv show ",
        "watching tv show ",
        "watching ",
        "following the tv show ",
        "following ",
        "the tv show ",
        "tv show ",
    )
    for prefix in prefixes:
        if existing.startswith(prefix):
            existing = existing[len(prefix):].strip()
            break
    return existing == target


class MemoryRecallMixin:
    @staticmethod
    def is_interest_recall_question(text):
        """Recognize broad and topic-specific personal-interest recall questions."""
        question = " ".join(
            re.sub(r"[?.!]", " ", str(text or "").lower()).split()
        )
        return bool(
            re.search(
                r"^what (?:personal )?(?:interests and hobbies|hobbies and interests) "
                r"have i (?:explicitly )?told you about\b",
                question
            )
            or _TOPIC_ACTIVITY_QUESTION.fullmatch(question)
            or _INTEREST_QUESTIONS.fullmatch(question)
        )

    @staticmethod
    def is_project_history_question(text):
        value = " ".join(
            re.sub(r"[?.!,]", " ", str(text or "").lower()).split()
        )
        # Both broad project lists and detailed questions about a named
        # project must use evidence-grounded SQLite recall. The full question
        # patterns below are specific enough that words such as "purpose",
        # "features", or "development decisions" must not disable routing.
        return bool(re.search(
            r"\bwhat projects have i (?:actually )?(?:told you|built|worked on|developed)\b|"
            r"\bwhat (?:projects|project) have i (?:built|worked on|developed)\b|"
            r"\bwhat do you remember about my .{0,50}project\b|"
            r"\bwhat have i told you about my .{0,50}project\b",
            value
        ))

    def is_project_history_followup(self, text):
        """Recognize a short project-name follow-up to a project-history query."""
        value = " ".join(
            re.sub(r"[?.!,]", " ", str(text or "").lower()).split()
        )
        match = re.fullmatch(
            r"(?:what about|tell me more about|and) ([a-z0-9_-]{2,40})",
            value
        )
        if not match:
            return False

        messages = self._recent_conversation_messages(limit=30)
        if messages and messages[-1][0] == "user" and _norm(messages[-1][1]) == _norm(text):
            messages = messages[:-1]
        previous_user_queries = [
            content for role, content in messages
            if role == "user" and str(content).strip()
        ]
        if not previous_user_queries or not self.is_project_history_question(
            previous_user_queries[-1]
        ):
            return False

        alias = match.group(1)
        known_projects = [
            str(item).strip().lower()
            for item in (self._facts_by_key().get("project", []) or [])
        ]
        return alias in known_projects


    def answer_project_history(self, query):
        """Answer project-history questions from user-authored SQLite transcript only."""
        if not (
            self.is_project_history_question(query)
            or self.is_project_history_followup(query)
        ):
            return None

        messages = self._recent_conversation_messages(limit=1000)
        if messages and messages[-1][0] == "user" and _norm(messages[-1][1]) == _norm(query):
            messages = messages[:-1]

        # A project may be explicitly mentioned in the transcript even when
        # the fact detector did not create a separate "project" row. Recover
        # only names directly labelled as projects by the user's own words.
        aliases = [
            str(value).strip()
            for value in (self._facts_by_key().get("project", []) or [])
            if len(str(value).strip()) >= 3
            and _norm(value) not in {"a project", "personal project", "a personal project", "project"}
        ]
        for role, content in messages:
            if role != "user":
                continue
            for pattern in (
                r"\b([A-Z][A-Z0-9_-]{1,30})\s+(?:is|was)\s+(?:a|the)\s+project\b",
                r"\b(?:my|the)\s+project\s+([A-Z][A-Za-z0-9._-]{1,40})\b",
                r"\b([A-Z][A-Z0-9_-]{1,30})\s+project\b",
            ):
                for match in re.finditer(pattern, content):
                    candidate = match.group(1).strip()
                    if len(candidate) >= 3 and _norm(candidate) not in {
                        "the", "my", "this", "that", "one"
                    } and not any(_norm(existing) == _norm(candidate) for existing in aliases):
                        aliases.append(candidate)

        confirmed = []
        for alias in aliases:
            matching = []
            purposes = []
            alias_pattern = re.compile(
                r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])",
                re.IGNORECASE
            )
            for role, content in messages:
                if role != "user" or not alias_pattern.search(content):
                    continue
                # Questions about a project are requests for recall, not
                # evidence that establishes its purpose or features.
                if re.match(
                    r"\s*(?:what|how|why|when|where|which|who|can you|could you|"
                    r"would you|do you|did you|is|are|was|were)\b",
                    content,
                    re.IGNORECASE
                ):
                    continue
                if not re.search(
                    r"\b(?:project|working on|worked on|building|built|"
                    r"developing|developed|creating|created|want|wants|"
                    r"should|need|needs|chose|chosen|decided|selected|"
                    r"has|have|includes|supports|provides|allows|"
                    r"prefer|preferred|planning)\b",
                    content,
                    re.IGNORECASE
                ):
                    continue

                matching.append(self._sentence_excerpt(content, max_chars=420))

                # Extract a purpose only from the same user-authored statement
                # that explicitly anchors this project. In particular, phrases
                # such as "You are my personal AI assistant" establish NEXUS's
                # purpose; unrelated interests and assistant-generated text do not.
                if re.search(
                    r"\b(?:you are|you're)\s+(?:my\s+)?personal\s+"
                    r"(?:ai\s+)?assis{1,2}tant\b|"
                    r"\bmy\s+personal\s+(?:ai\s+)?assis{1,2}tant\b",
                    content,
                    re.IGNORECASE
                ):
                    purposes.append("Personal AI assistant")

            if matching:
                confirmed.append((
                    alias,
                    list(dict.fromkeys(matching))[-5:],
                    list(dict.fromkeys(purposes))
                ))

        if not confirmed:
            return (
                "I don't have enough user-authored evidence in my stored "
                "conversation to identify a project you explicitly said you "
                "worked on. I won't infer one from computer details, assistant "
                "suggestions, or unrelated activity."
            )

        sections = ["Projects you explicitly said you were working on:"]
        for alias, evidence, purposes in confirmed:
            sections.append(f"\n{alias}")
            sections.extend(f"- You said: {item}" for item in evidence)
            if purposes:
                sections.append("- Purpose: " + "; ".join(purposes) + ".")
            else:
                sections.append(
                    "- Purpose and additional features: not established by "
                    "the user-authored statements retrieved here."
                )
        return "\n".join(sections)

    @staticmethod
    def is_associative_insight_question(text):
        """Identify questions that must be answered from SQLite evidence only."""
        question = " ".join(
            re.sub(r"[?!.]", " ", str(text or "").lower()).split()
        )
        question = re.sub(r"\s+only mention connections supported by things.*$", "", question)
        return bool(re.fullmatch(
            r"(?:what patterns have you noticed(?: about me| about my interests)?|"
            r"what patterns do you see(?: in my interests)?|"
            r"what themes keep coming up|what recurring themes do you see|"
            r"what have you noticed about my interests|"
            r"analyse my memories|analyze my memories|"
            r"how are my interests connected|"
            r"how are my interests and goals connected|"
            r"how are my goals and interests connected|"
            r"what connections have you found between my memories|"
            r"what connections (?:do you see|have you found) between my "
            r"(?:interests(?:,?\s*goals?)?(?:,?\s*and projects?)?|"
            r"goals?(?:,?\s*and projects?)?|projects?)|"
            r"what is the relationship between my interests and goals|"
            r"show my memory connections|connect my memories)",
            question
        ))
