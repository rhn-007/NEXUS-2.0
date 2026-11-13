import re



# Words after "my name is" that are not a name.
_NOT_A_NAME = {
    "not", "what", "is", "the", "a", "an", "none", "unknown", "secret",
    "important", "nothing", "and", "your", "my"
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

            if name.group(1) not in _NOT_A_NAME:

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

            r"my favou?rite ([a-z ]+?) is ([^.,]+)",

            text

        )


        for key,value in favorites:


            memories.append(

                {
                    "key": key.strip().replace(
                        " ",
                        "_"
                    ),

                    "value": value.strip()

                }

            )







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
            r"|\bmy project is\s+(?:called\s+)?"
            r"([a-z0-9][a-z0-9 _\-]*?)"
            r"(?=\s*(?:[,.;!]|$)|\s+(?:and|which|that|it|for)\b)",
            text
        )

        if project:

            name = (project.group(1) or project.group(2)).strip()

            if name and name not in _NOT_A_NAME:
                memories.append(
                    {"key": "project", "value": name}
                )

        # ==========================
        # PREFERENCES
        # ==========================

        preferences = re.findall(
            r"\bi prefer\s+([^.,;!]+)",
            text
        )

        preferences += re.findall(
            r"\bi want\s+((?:shorter|short|brief|concise|detailed|longer|"
            r"simple|simpler)\s+(?:answers|explanations|replies|responses))",
            text
        )

        preferences += re.findall(
            r"\bkeep\s+(?:your |the )?((?:answers|explanations|replies|"
            r"responses)\s+(?:short|brief|concise|simple))",
            text
        )

        for item in preferences:

            item = item.strip()[:80]

            if item:
                memories.append(
                    {"key": "preference", "value": item}
                )

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
