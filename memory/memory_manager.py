from memory.database import MemoryDatabase



class MemoryManager:


    def __init__(self):

        self.db = MemoryDatabase()



    def remember(
        self,
        key,
        value
    ):

        return self.db.insert(
            key,
            value
        )



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



    def save_memory(
        self,
        text
    ):

        return self.db.insert(
            "memory",
            text
        )



    def save_conversation(
        self,
        user,
        assistant
    ):

        self.db.insert(
            "user",
            user
        )


        self.db.insert(
            "assistant",
            assistant
        )



    def get_context(
        self
    ):


        results = self.db.search(
            ""
        )


        return results[-10:]
