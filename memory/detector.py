import re



# Words after "my name is" that are not a name.
_NOT_A_NAME = {
    "not", "what", "is", "the", "a", "an", "none", "unknown", "secret",
    "important", "nothing", "and", "your", "my", "i", "me"
}

# "i am tired" is a state, not a name.
_NOT_A_NAME_CASUAL = _NOT_A_NAME | {
    "tired", "hungry", "happy", "sad", "fine", "good", "great", "well",
    "ok", "okay", "sorry", "back", "here", "there", "ready", "bored",
    "busy", "sick", "late", "done", "sure", "confused", "angry", "excited",
    "free", "alone", "scared", "lost", "right", "wrong", "very", "so",
    "too", "just", "also", "still", "always", "never", "currently",
    "going", "able", "glad", "proud", "afraid", "curious", "interested",
    "new", "old", "young", "in", "on", "at", "from", "to", "about", "his",
    "her", "our", "their", "who", "student", "teacher", "engineer",
    "developer", "programmer"
}

_NAME_ENDINGS = ("ing", "ed", "ly", "ful", "ous", "ive", "ish", "ble")

_NOT_A_STATEMENT = re.compile(
    r"^(?:what|who|why|how|when|where|which|do|does|did|can|could|would|"
    r"should|is|are|will)\b"
)


def _looks_like_name(word):

    return (
        len(word) >= 2
        and word not in _NOT_A_NAME_CASUAL
        and not word.endswith(_NAME_ENDINGS)
    )


class MemoryDetector:



    def detect(
        self,
        text
    ):


        if not text:

            return []



        text = text.lower().strip()

        # Questions and "forget ..." are not things to remember.
        if (
            text.endswith("?")
            or "forget" in text
            or _NOT_A_STATEMENT.match(text)
        ):
            return []


        memories = []



        # ==========================
        # NAME
        # ==========================

        name = re.search(
            r"\bmy name is\s+([a-z]+)",
            text
        )

        casual = re.search(
            r"\b(?:i am|i'm)\s+([a-z]+)",
            text
        )

        if name:

            if _looks_like_name(name.group(1)):

                memories.append(
                    {"key": "name", "value": name.group(1)}
                )

        elif casual and _looks_like_name(casual.group(1)):

            memories.append(
                {"key": "name", "value": casual.group(1)}
            )

        # ==========================
        # INTERESTS
        # ==========================

        interests = re.findall(

            r"(?:i like|i love|i enjoy)\s+([^.,]+)",

            text

        )


        for item in interests:


            memories.append(

                {
                    "key": "interest",

                    "value": item.strip()

                }

            )







        # ==========================
        # FAVORITES
        # ==========================

        favorites = re.findall(

            r"my favou?rite ([a-z ]+?) (?:is|was) ([^.,]+)",

            text

        )


        for key,value in favorites:


            memories.append(

                {
                    "key": key.strip().replace(
                        " ",
                        "_"
                    ),

                    "value": re.sub(
                        r"\s+instead$",
                        "",
                        value.strip()
                    ).strip()

                }

            )

        # Understand explicit corrections to a previously stated favourite.
        # The replacement value is stored under the original field's key so
        # single-value memory naturally supersedes the older fact.
        correction_patterns = (
            (
                r"\bi (?:no longer|don't|do not) prefer\s+"
                r"[^.,;!]+?\s+as my favou?rite\s+([a-z ]+?)"
                r"\s*[.!?].*?\bmy (?:new )?favou?rite is\s+"
                r"([^.,;!]+)"
            ),
            (
                r"\bi(?:'ve| have) changed my favou?rite\s+"
                r"([a-z ]+?)\s+from\s+[^.,;!]+?\s+to\s+"
                r"([^.,;!]+)"
            ),
        )

        for pattern in correction_patterns:
            correction = re.search(pattern, text)
            if correction:
                key = correction.group(1).strip().replace(" ", "_")
                value = correction.group(2).strip()
                memories = [
                    memory for memory in memories
                    if memory["key"] != key
                ]
                memories.append({"key": key, "value": value})
                break







        # ==========================
        # CODING
        # ==========================

        if re.search(

            r"\bi (?:code|program|develop|write code)\b.*\bpython\b"
            r"|\b(?:i use|i'm using|i am using|i'm learning|"
            r"i am learning|i know|i love|i like)\s+python\b",

            text

        ):


            if "python" in text:


                memories.append(

                    {
                        "key": "coding",

                        "value": "python"

                    }

                )







        # ==========================
        # PROJECT (only when he gives its name)
        # ==========================

        project = re.search(
            r"\b(?:working on|building|developing|making)\s+"
            r"(?:a |an |the |my )?project\s+(?:called|named)\s+"
            r"([a-z0-9][a-z0-9 _\-]*?)"
            r"(?=\s*(?:[,.;!]|$)|\s+(?:and|which|that|it|for)\b)"
            r"|\bmy\s+(?:[a-z0-9]+\s+){0,3}project\s+"
            r"(?:is\s+(?:(?:called|named)\s+)?|(?:called|named)\s+)"
            r"([a-z0-9][a-z0-9 _\-]*?)"
            r"(?=\s*(?:[,.;!]|$)|\s+(?:and|which|that|it|for)\b)"
            r"|\bthe name of my\s+(?:[a-z0-9]+\s+){0,3}project\s+is\s+"
            r"(?:called\s+|named\s+)?"
            r"([a-z0-9][a-z0-9 _\-]*?)"
            r"(?=\s*(?:[,.;!]|$)|\s+(?:and|which|that|it|for)\b)",
            text
        )

        if project:

            name = (project.group(1) or project.group(2) or project.group(3)).strip()

            if name and name not in _NOT_A_NAME:
                memories.append(
                    {"key": "project", "value": name}
                )

        # ==========================
        # STRUCTURED PREFERENCES
        # "I prefer Java as my programming language" is a single-value fact,
        # not a general communication preference.
        structured_preferences = list(re.finditer(
            r"\bi(?:\s+actually)? prefer\s+([^.,;!]+?)"
            r"(?:\s+over\s+[^.,;!]+?)?\s+as my\s+"
            r"([a-z ]+?)(?:\s+over\s+[^.,;!]+)?(?=[.!?]|$)",
            text
        ))

        for match in structured_preferences:
            value = match.group(1).strip()
            key = match.group(2).strip().replace(" ", "_")
            if value and key:
                memories = [
                    memory for memory in memories
                    if memory["key"] != key
                ]
                memories.append({"key": key, "value": value})

        # GENERAL PREFERENCES
        # Remove structured preference clauses before extracting general ones.
        preference_text = text
        for match in reversed(structured_preferences):
            preference_text = (
                preference_text[:match.start()]
                + " "
                + preference_text[match.end():]
            )

        preferences = re.findall(
            r"\bi prefer\s+([^.,;!]+)",
            preference_text
        )

        preferences += re.findall(
            r"\bi want\s+((?:shorter|short|brief|concise|detailed|longer|"
            r"simple|simpler)\s+(?:answers|explanations|replies|responses))",
            preference_text
        )

        preferences += re.findall(
            r"\bkeep\s+(?:your |the )?((?:answers|explanations|replies|"
            r"responses)\s+(?:short|brief|concise|simple))",
            preference_text
        )

        for item in preferences:
            item = item.strip()[:80]
            if item:
                memories.append(
                    {"key": "preference", "value": item}
                )

        # Explicit corrections to general communication preferences.
        # Only replace a prior value when the user clearly contrasts the old
        # preference with a new one; ordinary preference statements remain
        # additive and are never treated as implicit corrections.
        preference_corrections = (
            re.search(
                r"\\bi (?:no longer|don't|do not) prefer\\s+"
                r"([^.,;!?]+)[.!?;]+\\s*(?:but\\s*)?"
                r"i (?:now )?prefer\\s+([^.,;!?]+)",
                text
            ),
            re.search(
                r"\\bi used to prefer\\s+([^.,;!?]+)[,;]+\\s*"
                r"but (?:now )?i prefer\\s+([^.,;!?]+)",
                text
            ),
        )
        correction = next(
            (match for match in preference_corrections if match),
            None
        )
        if correction:
            old_value = correction.group(1).strip()[:80]
            new_value = correction.group(2).strip()[:80]
            if old_value and new_value and old_value != new_value:
                memories = [
                    memory for memory in memories
                    if memory["key"] != "preference"
                ]
                memories.append({
                    "key": "preference",
                    "value": new_value,
                    "replaces": old_value
                })

        # ==========================
        # REMOVE DUPLICATES
        # ==========================

        result = []

        seen = set()


        for memory in memories:


            check = (

                memory["key"],

                memory["value"]

            )


            if check not in seen:


                seen.add(check)

                result.append(memory)



        return result

    def detect_answer(self, answer, previous_question):
        """
        Resolve a short answer only when the previous user message clearly
        asked for a favourite fact, such as "what is my favourite sport?".
        """
        if not answer or not previous_question:
            return []

        question = re.sub(r"[?.!,]", " ", str(previous_question).lower())
        question = " ".join(question.split())
        question_match = re.fullmatch(
            r"what(?:'s| is) my favou?rite ([a-z][a-z ]{0,30})",
            question
        )
        if not question_match:
            return []

        answer_text = str(answer).lower().strip()
        # Accept a direct answer followed by an additional sentence, e.g.
        # "It's badminton. I like badminton." Keep only the answer clause.
        answer_match = re.match(
            r"(?:it is|it's|it’s|the answer is)\s+"
            r"([a-z][a-z0-9' -]{0,59}?)"
            r"(?=\s*[.!?](?:\s|$)|$)",
            answer_text
        )
        if not answer_match:
            return []

        key = question_match.group(1).strip().replace(" ", "_")
        value = answer_match.group(1).strip(" .!?")
        if not key or not value:
            return []

        return [{"key": key, "value": value}]
