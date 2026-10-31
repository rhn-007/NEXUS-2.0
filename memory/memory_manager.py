from memory.database import MemoryDatabase
from memory.detector import MemoryDetector



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
    
    
    
        for memory in memories:
    
    
            self.db.insert(
    
                memory["key"],
    
                memory["value"],
    
                "fact"
    
            )
    
    
    
        return True





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


        return self.db.search(

            ""

        )
