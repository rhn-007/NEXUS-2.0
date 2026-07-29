from memory.database import MemoryDatabase



class MemoryManager:


    def __init__(self):

        self.db = MemoryDatabase()



    # =====================================
    # SAVE A MEMORY FACT
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
    # RECALL SPECIFIC MEMORY
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
    # SAVE AUTOMATIC MEMORY
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
    # SAVE CONVERSATIONS
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



        # Save user message

        self.db.insert(

            "user",

            user,

            "conversation"

        )



        # Avoid storing useless AI replies

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
    # GET CHAT CONTEXT
    # =====================================

    def get_context(
        self
    ):


        results = self.db.search(

            "conversation"

        )


        return results[-10:]



    # =====================================
    # GET ALL MEMORY FACTS
    # =====================================

    def get_memory_context(
        self
    ):


        results = self.db.search(

            "memory"

        )


        return results
