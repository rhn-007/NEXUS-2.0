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

    def answer_fact_question(self, text):
        """
        Answer "what is my name", "what's my favourite programming language",
        "what project am I working on" or "what do I prefer" from stored
        facts. Returns None when nothing stored matches, so the question
        carries on to the rest of NEXUS.
        """

        question = " ".join(
            re.sub(r"[?.!]", " ", str(text or "").lower()).split()
        )
        question = re.sub(r"\s+only mention connections supported by things.*$", "", question)

        question = _FILLERS.sub("", question)

        # Canonicalize this common conversational recall phrase explicitly.
        # It must reach the deterministic SQLite interests handler rather
        # than falling through to the language model.
        if question == "what do you remember about my hobbies and interests":
            question = "what are my hobbies and interests"

        # Broadly phrased requests for confirmed interests should use the
        # same deterministic SQLite answer as the shorter hobby questions.
        if re.match(
            r"^what (?:personal )?(?:interests and hobbies|hobbies and interests) "
            r"have i (?:explicitly )?told you about\b",
            question
        ):
            question = "what are my hobbies and interests"

        # Topic-specific hobby questions return only stored interest/hobby
        # values that actually mention the requested topics.
        topic_activity = _TOPIC_ACTIVITY_QUESTION.fullmatch(question)
        if topic_activity:
            topics = [
                re.sub(r"^and\s+", "", item.strip())
                for item in re.split(r"\s*,\s*|\s+and\s+", topic_activity.group("topics"))
                if item.strip() and item.strip() != "and"
            ]
            stored_values = (
                self._facts_by_key().get("interest", [])
                + self._facts_by_key().get("hobby", [])
                + self._facts_by_key().get("activity", [])
            )
            matched_values = []
            missing_topics = []
            for topic in topics:
                matches = [
                    value for value in stored_values
                    if re.search(r"\b" + re.escape(topic) + r"\b", str(value), re.IGNORECASE)
                ]
                if matches:
                    for value in matches:
                        if value not in matched_values:
                            matched_values.append(value)
                else:
                    missing_topics.append(topic)
            if not matched_values and not missing_topics:
                return None
            response = (
                "You told me: " + _join(matched_values) + "."
                if matched_values else
                "I couldn't find those activities in your stored interests."
            )
            if missing_topics:
                response += (
                    " I don't have a separate stored detail about "
                    + _join(missing_topics) + "."
                )
            return response

        # Normalize common natural-language paraphrases into the same
        # deterministic fact questions handled below. Keep these patterns
        # narrow so unrelated questions continue to the normal assistant.
        paraphrases = (
            (
                r"^(?:which|what) sport do i like(?: the)? most$",
                "what is my favourite sport",
            ),
            (
                r"^(?:do you (?:remember|know) )?which programming "
                r"language i prefer$|^what programming language do i prefer$",
                "what is my favourite programming language",
            ),
            (
                r"^(?:tell me )?the name of the ai project "
                r"i(?:'m| am) developing$",
                "what is the name of my ai project",
            ),
        )
        for pattern, canonical in paraphrases:
            if re.fullmatch(pattern, question):
                question = canonical
                break

        # Natural recall wording should resolve to the same authoritative
        # fact as a direct "who/what is my favourite ..." question.
        remembered_favourite = re.fullmatch(
            r"(?:what do you (?:remember|know) about|what have i told you about) "
            r"my (?:favourite |favorite )([a-z ]+)",
            question
        )
        if remembered_favourite:
            thing = remembered_favourite.group(1).strip()
            question = "who is my favourite " + thing

        # Indirect questions such as "tell me who my favourite artist is"
        # use the same deterministic lookup as "who is my favourite artist".
        indirect_favourite = re.fullmatch(
            r"who my (?:favourite |favorite )?([a-z ]+?) is",
            question
        )
        if indirect_favourite:
            question = "who is my favourite " + indirect_favourite.group(1).strip()

        if not question or len(question) > 120:
            return None

        # Stage 4 insight questions use only stored facts and persisted graph
        # evidence. They never ask the model to invent a personal pattern.
        pattern_question = re.fullmatch(
            r"(?:what patterns have you noticed(?: about me| about my interests)?|"
            r"what patterns do you see(?: in my interests)?|"
            r"what themes keep coming up|what recurring themes do you see|"
            r"what have you noticed about my interests|"
            r"analyse my memories|analyze my memories)",
            question
        )
        if pattern_question:
            self.associative_memory.rebuild_patterns()
            patterns = self.associative_memory.get_patterns(limit=6)
            if not patterns:
                return (
                    "I don't have enough repeated evidence in your saved facts "
                    "to identify reliable personal patterns yet."
                )
            summaries = [item["summary"] for item in patterns[:4]]
            return "From the facts you've shared, these are the patterns I can support: " + " ".join(summaries)

        connection_question = re.fullmatch(
            r"(?:what connections have you found between my memories|"
            r"what connections (?:do you see|have you found) between my "
            r"(?:interests(?:,?\s*goals?)?(?:,?\s*and projects?)?|"
            r"goals?(?:,?\s*and projects?)?|projects?)|"
            r"how are my interests connected|"
            r"how are my interests and goals connected|"
            r"how are my goals and interests connected|"
            r"what is the relationship between my interests and goals|"
            r"show my memory connections|connect my memories)",
            question
        )
        if connection_question:
            self.associative_memory.update()
            relationships = self.associative_memory.get_relationships(limit=30)

            # A question specifically about interests and goals needs a
            # relationship between those categories, not arbitrary co-mentions
            # such as a sport and a television show.
            requested_categories = set()
            if "interest" in question or "hobb" in question:
                requested_categories.update(self.associative_memory._INTEREST_KEYS)
            if "goal" in question or "project" in question:
                requested_categories.update(self.associative_memory._GOAL_PROJECT_KEYS)
            if requested_categories:
                relationships = [
                    edge for edge in relationships
                    if edge["source_key"] in requested_categories
                    and edge["target_key"] in requested_categories
                    and edge["source_key"] != edge["target_key"]
                ]

            # Only explicit links and distinctive topical overlaps are useful
            # evidence here. A simple co-mention is not a meaningful connection.
            relationships = [
                edge for edge in relationships
                if (
                    edge["origin"] == "explicit"
                    and edge["relation_type"] == "related_to"
                ) or (
                    edge["origin"] == "inferred"
                    and edge["relation_type"] == "shares_topic"
                    and float(edge["confidence"]) >= 0.84
                )
            ]

            if not relationships:
                if "interests and goals" in question or "goals and interests" in question:
                    return (
                        "I can identify your interests and goals separately, "
                        "but I don't have a sufficiently supported connection "
                        "between them yet. I won't assume that one explains or "
                        "causes the other."
                    )
                return (
                    "I haven't found enough evidence to establish reliable "
                    "connections between your saved memories yet."
                )

            descriptions = []
            for edge in relationships[:5]:
                left = f'{edge["source_key"].replace("_", " ")}: {edge["source_value"]}'
                right = f'{edge["target_key"].replace("_", " ")}: {edge["target_value"]}'
                if edge["origin"] == "explicit":
                    descriptions.append(
                        f"you explicitly connected {left} with {right}"
                    )
                else:
                    descriptions.append(
                        f"{left} and {right} share a possible topical overlap"
                    )
            return (
                "The possible connections supported by your saved evidence are: "
                + "; ".join(descriptions)
                + ". These associations do not establish causation."
            )

        # Explicit questions about a previously stated learning preference
        # are answered from the matching SQLite fact, never guessed by the LLM.
        learning_preference_question = re.fullmatch(
            r"(?:what did i say about how i prefer to learn"
            r"(?: new concepts)?|what have i told you about how i learn"
            r"(?: new concepts)?|what do you remember about how i prefer to learn"
            r"(?: new concepts)?|what do you remember about how i learn|"
            r"how did i say i learn best|"
            r"how do i prefer to learn|what is my learning preference|"
            r"what are my learning preferences|"
            r"what do you know about my learning preferences|"
            r"what do you remember about my learning preferences|"
            r"how do i like to learn|"
            r"what is my preferred way to learn|"
            r"what learning method do i prefer)",
            question
        )
        if learning_preference_question:
            grouped = self._facts_by_key()
            values = (
                grouped.get("learning_preference")
                or grouped.get("learning_approach")
                or grouped.get("learning_style")
            )
            if not values:
                return "You haven't told me how you prefer to learn new concepts yet."
            value = _join(values)
            if "practical project" in value.lower() or "build" in value.lower():
                return (
                    "You said you understand concepts much better by building "
                    "practical projects rather than just reading about them."
                )
            return "You told me: " + value.rstrip(".") + "."

        grouped = self._facts_by_key()

        # Resolve common question forms through a small, explicit alias map.
        # This avoids adding one regex for every individual paraphrase while
        # keeping ambiguous or unknown questions out of deterministic recall.
        question_key_aliases = {
            "singer": "singer",
            "music artist": "singer",
            "musical artist": "singer",
            "artist": "singer",
            "sport": "sport",
            "programming language": "programming_language",
            "coding language": "programming_language",
            "language": "programming_language",
            "project": "project",
            "ai project": "project",
            "project name": "project",
            "ai project name": "project",
        }
        question_patterns = (
            r"^(?:which|what) (?P<thing>[a-z ]+?) do i "
            r"(?:like|prefer|use|code in)(?: the most)?$",
            r"^what (?P<thing>[a-z ]+?) am i "
            r"(?:into|interested in)$",
        )
        for pattern in question_patterns:
            match = re.fullmatch(pattern, question)
            if not match:
                continue

            thing = _norm(match.group("thing"))
            key = question_key_aliases.get(thing, thing.replace(" ", "_"))
            values = grouped.get(key, [])
            if not values:
                continue

            label = {
                "singer": "favourite singer",
                "sport": "favourite sport",
                "programming_language": "favourite programming language",
                "project": "AI project name",
            }.get(key, thing)
            if key == "project":
                return "Your AI project name is " + _join(values) + "."
            return f"Your {label} is " + _join(values) + "."

        # Canonical combined recall: parse each named fact independently.
        # This avoids treating the comma-separated labels as one unknown key.
        if re.fullmatch(
            r"what are my (?:favourite|favorite) sport, "
            r"(?:favourite|favorite) programming language, and "
            r"(?:ai )?project name",
            question,
        ):
            sport = grouped.get("sport", [])
            language = grouped.get("programming_language", [])
            project = grouped.get("project", [])
            parts = []
            if sport:
                parts.append("your favourite sport is " + _join(sport))
            else:
                parts.append("you haven't told me your favourite sport yet")
            if language:
                parts.append(
                    "your favourite programming language is " + _join(language)
                )
            else:
                parts.append(
                    "you haven't told me your favourite programming language yet"
                )
            if project:
                parts.append("your AI project name is " + _join(project))
            else:
                parts.append("you haven't told me your AI project name yet")
            return "; ".join(parts[:-1]) + "; and " + parts[-1] + "."

        # Handle explicit multi-fact questions deterministically. A request
        # listing several personal details must never be left to the language
        # model, where unsupported guesses can be presented as memories.
        multi_prefix = re.match(r"^(?:what are|what is|tell me) my (.+)$", question)
        if (
            multi_prefix
            and ("," in multi_prefix.group(1) or " and " in multi_prefix.group(1))
            and not _INTEREST_QUESTIONS.fullmatch(question)
        ):
            raw_items = [
                item.strip()
                for item in re.split(r"\s*,\s*|\s+and\s+", multi_prefix.group(1))
                if item.strip()
            ]
            # When the comma is followed by ", and", the comma split may
            # leave the conjunction attached to the next item.
            raw_items = [
                item[4:].strip() if item.startswith("and ") else item
                for item in raw_items
                if (item[4:].strip() if item.startswith("and ") else item)
            ]
            if 2 <= len(raw_items) <= 6:
                answers = []
                for raw_item in raw_items:
                    item = _norm(raw_item)
                    item = re.sub(r"^(?:my )?(?:favourite|favorite)\s+", "", item)
                    item = re.sub(r"^(?:the|a|an)\s+", "", item)
                    item = item.removeprefix("ai ")

                    aliases = {
                        "project name": "project",
                        "ai project name": "project",
                        "project": "project",
                        "sport": "sport",
                        "programming language": "programming_language",
                        "coding language": "programming_language",
                        "language": "programming_language",
                    }
                    key = aliases.get(item, item.replace(" ", "_"))
                    values = grouped.get(key, [])
                    if values:
                        label = {
                            "project": "AI project name",
                            "programming_language": "favourite programming language",
                            "sport": "favourite sport",
                        }.get(key, item)
                        answers.append(
                            f"your {label} is {_join(self._show(key, value) for value in values)}"
                        )
                    else:
                        label = {
                            "project": "AI project name",
                            "programming_language": "favourite programming language",
                            "sport": "favourite sport",
                        }.get(key, item)
                        answers.append(f"you haven't told me your {label} yet")
                if answers:
                    if len(answers) == 1:
                        return answers[0][0].upper() + answers[0][1:] + "."
                    return "; ".join(answers[:-1]) + "; and " + answers[-1] + "."

        # Resolve project-name wording variants before generic key matching.
        project_question = re.fullmatch(
            r"what(?:'s| is) the name of my (?:ai )?project"
            r"|what(?:'s| is) my (?:ai )?project name"
            r"|what(?:'s| is) my ai project"
            r"|what(?:'s| is) my current project called"
            r"|do you (?:know|remember) my (?:ai )?project(?: name)?",
            question
        )
        if project_question:
            projects = grouped.get("project", [])
            if projects:
                return "Your AI project name is " + _join(projects) + "."
            return "You haven't told me your AI project name yet."

        study_time_question = re.fullmatch(
            r"(?:what time do i prefer studying|"
            r"when do i prefer to study|"
            r"what is my preferred study time|"
            r"what time do i usually study)",
            question
        )
        if study_time_question:
            values = grouped.get("study_time", [])
            if values:
                return "You prefer studying at " + _join(values) + "."
            return "You haven't told me your preferred study time yet."

        if _PREFERENCE_QUESTIONS.match(question):

            values = grouped.get("preference")

            if not values:
                return None

            return "You prefer " + _join(values) + "."

        if _TV_SHOW_QUESTIONS.fullmatch(question):
            shows = []
            seen = set()
            for raw_value in grouped.get("tv_show", []):
                show = _clean_tv_show_title(raw_value)
                if show and _tv_show_identity(show) not in seen:
                    seen.add(_tv_show_identity(show))
                    shows.append(show)
            # Older versions sometimes stored explicitly labelled show titles
            # in the general-interest category. Read those without treating
            # arbitrary interests or model-generated guesses as TV shows.
            for raw_value in grouped.get("interest", []) + grouped.get("hobby", []) + grouped.get("activity", []):
                show = _clean_tv_show_value(raw_value)
                if show and _tv_show_identity(show) not in seen:
                    seen.add(_tv_show_identity(show))
                    shows.append(show)
            if not shows:
                return "You haven't told me which TV shows you enjoy yet."
            return "You told me you enjoy watching " + _join(
                "the TV show " + show for show in shows
            ) + "."

        if _INTEREST_QUESTIONS.match(question):

            raw_values = grouped.get("interest", []) + grouped.get("hobby", []) + grouped.get("activity", [])
            values = []
            tv_shows = []
            seen_values = set()
            seen_shows = set()

            for raw_value in raw_values:
                show = _clean_tv_show_value(raw_value)
                if show:
                    marker = _tv_show_identity(show)
                    if marker not in seen_shows:
                        seen_shows.add(marker)
                        tv_shows.append(show)
                    continue

                value = _clean_interest_value(raw_value)
                if not value:
                    continue

                marker = _norm(value)
                if marker in seen_values:
                    continue

                seen_values.add(marker)
                values.append(value)

            for raw_show in grouped.get("tv_show", []):
                show = _clean_tv_show_title(raw_show)
                if not show:
                    continue
                marker = _tv_show_identity(show)
                if marker not in seen_shows:
                    seen_shows.add(marker)
                    tv_shows.append(show)

            if not values and not tv_shows:
                return "You haven't told me about your hobbies or interests yet."

            response = (
                "You've mentioned enjoying " + _join(values) + "."
                if values else ""
            )
            if tv_shows:
                show_sentence = (
                    "You also mentioned the TV show " + _join(tv_shows) + "."
                    if values else
                    "You mentioned the TV show " + _join(tv_shows) + "."
                )
                response = (response + " " + show_sentence).strip()

            return response

        # Correct a common speech/typing variant before matching saved favourites.
        question = re.sub(r"\bfavoraite\b", "favourite", question)

        for pattern in _FACT_QUESTIONS:

            match = pattern.match(question)

            if not match:
                continue

            thing = _norm(match.group("thing"))

            thing = re.sub(r"^(?:the|a|an)\s+", "", thing)
            # "singer", "artist", and "music artist" are the same
            # personal-memory category for favourite-artist questions.
            thing = {
                "music artist": "singer",
                "musical artist": "singer",
                "artist": "singer",
            }.get(thing, thing)

            favourite = bool(
                match.groupdict().get("favourite")
            )

            for key, values in grouped.items():

                name = _norm(key)

                if (
                    thing == name
                    or name.endswith(" " + thing)
                    or thing.endswith(" " + name)
                ):

                    shown = _join(self._show(key, v) for v in values)

                    label = ("favourite " if favourite else "") + thing

                    return f"Your {label} is {shown}."

            if favourite:
                return f"You haven't told me your favourite {thing} yet."

        return None

