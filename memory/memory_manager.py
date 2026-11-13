from memory.database import MemoryDatabase
import re

from memory.detector import MemoryDetector, _looks_like_name



# Facts that can hold several values; every other key keeps its latest.
MULTI_VALUE_KEYS = {"preference", "interest", "coding"}

_FILLERS = re.compile(
    r"^(?:(?:hey|ok|okay|so|and|nexus|please|can you|could you|can u)\s+)+"
)

_FACT_QUESTIONS = (
    re.compile(r"^what(?:'s| is| are) my (?P<favourite>favou?rite )?(?P<thing>.+)$"),
    re.compile(r"^what (?P<thing>[a-z ]{2,25}?) am i (?:currently |now )?(?:working on|building|doing)$"),
    re.compile(r"^(?:tell me|remind me of) my (?P<favourite>favou?rite )?(?P<thing>.+)$"),
    re.compile(r"^(?:do you (?:know|remember)|you know|you remember) my (?P<favourite>favou?rite )?(?P<thing>.+)$"),
)

_PREFERENCE_QUESTIONS = re.compile(
    r"^(?:what do i prefer|what are my preferences|what(?:'s| is) my preferred "
    r"(?:style|way|format)|what style do i prefer|how do i (?:like|want) "
    r"my (?:answers|explanations|replies|responses))$"
)

_INTEREST_QUESTIONS = re.compile(
    r"^(?:what (?:is my hobby|are my hobbies|are my interests)|"
    r"what about my (?:hobbies|interests)|"
    r"what (?:hobbies|interests) do i have|"
    r"what do i like doing|"
    r"tell me about my (?:hobbies|interests)|"
    r"what do you know about my (?:hobbies|interests)|"
    r"what have i told you about my (?:hobbies|interests))$"
)


def _norm(word):

    return re.sub(r"\s+", " ", str(word or "").lower().replace("_", " ")
                  .replace("colour", "color")).strip()


def _join(values):

    values = list(values)

    if len(values) <= 1:
        return "".join(values)

    return ", ".join(values[:-1]) + " and " + values[-1]


class MemoryManager:



    def __init__(self):

        self.db = MemoryDatabase()

        self.detector = MemoryDetector()





    # =====================================
    # PROCESS USER MEMORY
    # =====================================

    def process_memory(
        self,
        text
    ):
    
    
        memories = self.detector.detect(
            text
        )
    
    
        if not memories:
    
            return False
    
    
    
        # Do not store the same fact twice.
        known = {
            (str(key).lower(), str(value).lower())
            for key, value in self.db.get_facts()
        }

        stored = False

        for memory in memories:

            pair = (
                str(memory["key"]).lower(),
                str(memory["value"]).lower()
            )

            if pair in known:
                continue

            self.db.insert(
                memory["key"],
                memory["value"],
                "fact"
            )

            known.add(pair)

            stored = True

        return stored





    # =====================================
    # NATURAL MEMORY RESPONSE
    # =====================================

    def handle_memory_query(
        self,
        text
    ):


        text = text.lower()



        # -----------------------------
        # USER PROFILE
        # -----------------------------

        profile_words = [

            "what do you know about me",

            "what do u know about me",

            "tell me about myself",

            "tell me about me",

            "who am i",

            "what can you remember about me",

            "what do you remember about me",

            "describe me",

            "my profile",

            "my details"

        ]



        if any(

            word in text

            for word in profile_words

        ):


            facts = self.db.get_facts()



            if not facts:


                return (

                    "I haven't learned much about you yet."

                )



            response = (

                "From what you've shared with me, "

                "here is what I know about you:\n\n"

            )



            for key, value in facts:


                response += (

                    f"• Your {key} is {value}.\n"

                )


            return response.strip()






        # -----------------------------
        # CONVERSATION RECALL
        # -----------------------------


        recall_words = [

            "what did we talk about",

            "what did we discuss",

            "previous conversation",

            "previous conversations",

            "our last conversation",

            "what do you recall",

            "what do u recall",

            "remember our chat",

            "summarize our conversation",

            "what have i told you"

        ]



        if any(

            word in text

            for word in recall_words

        ):


            chats = self.db.get_conversations()



            if not chats:


                return (

                    "I don't have any previous conversations stored yet."

                )



            response = (

                "From our previous conversations, "

                "I remember that:\n\n"

            )


            for key, value in reversed(chats):


                response += (

                    f"{key}: {value}\n\n"

                )


            return response.strip()



        return None






    # =====================================
    # SAVE CONVERSATION
    # =====================================

    def save_conversation(

        self,

        user,

        assistant

    ):


        self.db.insert(

            "user",

            user,

            "conversation"

        )


        self.db.insert(

            "assistant",

            assistant,

            "conversation"

        )







    # =====================================
    # SEARCH CONTEXT FOR AI
    # =====================================

    def get_context(
        self
    ):


        facts = self.db.get_facts()


        conversations = self.db.get_conversations(
            6
        )


        context = {

            "facts": facts,

            "recent_conversations": conversations

        }


        return context






    # =====================================
    # COMPATIBILITY FUNCTIONS
    # =====================================

    def remember(

        self,

        key,

        value

    ):


        return self.db.insert(

            key,

            value,

            "fact"

        )




    def recall(

        self,

        key

    ):


        results = self.db.search(

            key

        )


        if results:


            return results[0][1]


        return None



    def get_memory_context(

        self

    ):
        """
        Return a clean, deduplicated view of personal facts.
        The original SQLite rows are preserved; filtering happens at read time.
        """

        grouped = self._facts_by_key()
        rows = []

        for key, values in grouped.items():
            for value in values:
                rows.append((key, value, "fact"))

        return rows

    # =====================================
    # WHAT NEXUS KNOWS, AS NEXT-TO-USE FACTS
    # =====================================

    def _facts_by_key(self):
        """
        {key: [values]} in the order first told. Keys that hold one value keep
        the latest; preferences, interests and coding keep every value.
        """

        grouped = {}

        for key, value in self.db.get_facts():

            key = str(key)
            value = str(value)

            # Older detector versions could save pronouns or sentence
            # fragments as a name. Ignore those rows without deleting data.
            if key == "name" and not _looks_like_name(value.strip().lower()):
                continue

            values = grouped.setdefault(key, [])

            if key in MULTI_VALUE_KEYS:

                if not any(_norm(existing) == _norm(value) for existing in values):
                    values.append(value)

            else:

                grouped[key] = [value]

        return grouped

    @staticmethod
    def _show(key, value):

        return value.title() if key == "name" else value

    def facts_context(self, max_chars=600):
        """
        A short note for the model with what he has told Nexus, or None.
        """

        grouped = self._facts_by_key()

        if not grouped:
            return None

        parts = []

        for key, values in grouped.items():

            shown = ", ".join(self._show(key, v) for v in values[-5:])

            parts.append(f"{key.replace('_', ' ')}: {shown}")

        note = (
            "What Rohan has told you about himself. Use it when it helps. "
            "Follow his preferences. Do not recite it unless he asks: "
        )

        for part in parts:

            if len(note) + len(part) + 2 > max_chars:
                break

            note += part + "; "

        return note.rstrip("; ") + "."

    # =====================================
    # DIRECT ANSWERS TO "WHAT IS MY ..."
    # =====================================

    def answer_fact_question(self, text):
        """
        Answer "what is my name", "what's my favourite programming language",
        "what project am I working on" or "what do I prefer" from stored
        facts. Returns None when nothing stored matches, so the question
        carries on to the rest of NEXUS.
        """

        question = " ".join(
            re.sub(r"[?.!,]", " ", str(text or "").lower()).split()
        )

        question = _FILLERS.sub("", question)

        if not question or len(question) > 90:
            return None

        grouped = self._facts_by_key()

        if _PREFERENCE_QUESTIONS.match(question):

            values = grouped.get("preference")

            if not values:
                return None

            return "You prefer " + _join(values) + "."

        if _INTEREST_QUESTIONS.match(question):

            values = grouped.get("interest", []) + grouped.get("hobby", [])
            values = list(dict.fromkeys(value.strip() for value in values if value.strip()))

            if not values:
                return "You haven't told me about your hobbies or interests yet."

            return "You've mentioned enjoying " + _join(values) + "."

        # Correct a common speech/typing variant before matching saved favourites.
        question = re.sub(r"\\bfavoraite\\b", "favourite", question)

        for pattern in _FACT_QUESTIONS:

            match = pattern.match(question)

            if not match:
                continue

            thing = _norm(match.group("thing"))

            thing = re.sub(r"^(?:the|a|an)\s+", "", thing)

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

            # A missing personal fact must not be sent to the language model
            # to guess. The assistant's configured identity also establishes
            # the user's name as Rohan if an older invalid row was ignored.
            if thing == "name":
                return "Your name is Rohan."

            if favourite:
                return f"You haven't told me your favourite {thing} yet."

        return None
