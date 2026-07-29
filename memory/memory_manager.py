from memory.database import MemoryDatabase
from memory.detector import MemoryDetector



class MemoryManager:


    def __init__(self):

        self.db = MemoryDatabase()

        self.detector = MemoryDetector()



    # =====================================
    # PROCESS USER INPUT FOR MEMORY
    # =====================================

    def process_memory(
        self,
        text
    ):


        memory = self.detector.detect(

            text

        )


        if memory:


            self.remember(

                memory["key"],

                memory["value"]

            )


            return True



        return False




    # =====================================
    # SAVE MEMORY FACT
    # =====================================

    def remember(
        self,
        key,
        value
    ):


        return self.db.insert(

            key,

            value,

            "memory"

        )




    # =====================================
    # RECALL MEMORY
    # =====================================

    def recall(
        self,
        key
    ):


        results = self.db.search(

            key

        )


        if not results:

            return None



        return results[0][1]




    # =====================================
    # OLD COMPATIBILITY FUNCTION
    # =====================================

    def save_memory(
        self,
        text
    ):


        return self.db.insert(

            "memory",

            text,

            "memory"

        )




    # =====================================
    # SAVE CONVERSATION
    # =====================================

    def save_conversation(
        self,
        user,
        assistant
    ):


        blocked_phrases = [

            "i don't have personal relationships",

            "i don't actually know you",

            "our conversation just started",

            "i don't have personal memories",

            "i am a conversational ai",

            "i don't have access to previous"

        ]



        self.db.insert(

            "user",

            user,

            "conversation"

        )



        if not any(

            phrase in assistant.lower()

            for phrase in blocked_phrases

        ):


            self.db.insert(

                "assistant",

                assistant,

                "conversation"

            )




    # =====================================
    # GET CONVERSATION CONTEXT
    # =====================================

    def get_context(
        self
    ):


        results = self.db.search(

            "conversation"

        )


        return results[-10:]




    # =====================================
    # GET ALL USER MEMORY
    # =====================================

    def get_memory_context(
        self
    ):


        return self.db.search(

            "memory"

        )
