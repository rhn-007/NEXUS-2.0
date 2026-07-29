from memory.database import MemoryDatabase


class MemoryManager:


    def __init__(self):

        self.db = MemoryDatabase()



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
