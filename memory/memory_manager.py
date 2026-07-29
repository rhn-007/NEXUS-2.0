from memory.database import MemoryDatabase


class MemoryManager:


    def __init__(self):

        self.db = MemoryDatabase()



    def save_memory(self, text):

        self.db.insert(
            "memory",
            text
        )


        return True



    def remember(
        self,
        key,
        value
    ):

        self.db.insert(
            key,
            value
        )

        return True



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



    def get_context(self):

        results = self.db.search(
            "memory"
        )


        memories = []


        for item in results:

            memories.append(
                item[1]
            )


        return memories



    def save_conversation(
        self,
        user,
        assistant
    ):

        self.db.insert(
            "conversation",
            f"User: {user}\nAssistant: {assistant}"
        )
