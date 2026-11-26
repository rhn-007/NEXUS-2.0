"""Deterministic answers to direct personal-fact questions."""

import re

from memory.recall import (
    _FILLERS,
    _FACT_QUESTIONS,
    _INTEREST_QUESTIONS,
    _PREFERENCE_QUESTIONS,
    _TOPIC_ACTIVITY_QUESTION,
    _TV_SHOW_QUESTIONS,
    _clean_interest_value,
    _clean_tv_show_title,
    _clean_tv_show_value,
    _join,
    _norm,
    _tv_show_identity,
)


class FactRecallMixin:
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
