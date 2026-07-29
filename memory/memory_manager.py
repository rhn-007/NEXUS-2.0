"""
NEXUS Memory Manager
"""


from memory.database import MemoryDatabase

from memory.detector import MemoryDetector





class MemoryManager:



    def __init__(self):


        self.db = MemoryDatabase()

        self.detector = MemoryDetector()




    def process_memory(
        self,
        text
    ):


        memories = self.detector.detect(

            text

        )


        for memory in memories:


            self.remember(

                memory["key"],

                memory["value"]

            )



    def remember(
        self,
        key,
        value
    ):


        return self.db.insert(

            key,

            value,

            "profile"

        )




    def recall(
        self,
        key
    ):


        result = self.db.search(

            key

        )


        if result:

            return result[0][1]


        return None




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




    def get_context(
        self
    ):


        return self.db.get_conversations()




    def get_memory_context(
        self
    ):


        return self.db.get_profile()
