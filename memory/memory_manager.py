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


        memories = self.detector.detect(text)



        for memory in memories:


            self.remember(

                memory["key"],

                memory["value"],

                memory["category"]

            )





    def remember(

        self,

        key,

        value,

        category="general"

    ):


        self.db.insert(

            key,

            value,

            category

        )





    def recall(

        self,

        keyword

    ):


        return self.db.search(keyword)





    def get_memory_context(self):


        return self.db.get_all()





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





    def get_context(self):


        return self.db.search(

            "conversation"

        )
