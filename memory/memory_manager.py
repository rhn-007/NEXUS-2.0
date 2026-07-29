"""
NEXUS Memory Manager

Controls:
- User facts
- Preferences
- Conversation history
"""

from memory.database import MemoryDatabase
from memory.detector import MemoryDetector



class MemoryManager:


    def __init__(self):

        self.db = MemoryDatabase()

        self.detector = MemoryDetector()



    # ==========================================
    # PROCESS MEMORY INPUT
    # ==========================================

    def process_memory(
        self,
        text
    ):


        detected = self.detector.detect(
            text
        )


        if not detected:

            return False



        self.remember(

            detected["key"],

            detected["value"]

        )


        return True



    # ==========================================
    # SAVE FACT / PREFERENCE
    # ==========================================

    def remember(
        self,
        key,
        value
    ):


        return self.db.insert(

            key,

            value,

            category="fact"

        )



    # ==========================================
    # RECALL MEMORY
    # ==========================================

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



    # ==========================================
    # SAVE CONVERSATION
    # ==========================================

    def save_conversation(
        self,
        user,
        assistant
    ):


        self.db.insert(

            "user",

            user,

            category="conversation"

        )


        self.db.insert(

            "assistant",

            assistant,

            category="conversation"

        )



    # ==========================================
    # GET CHAT HISTORY
    # ==========================================

    def get_context(
        self,
        limit=10
    ):


        return self.db.get_conversations(
            limit
        )



    # ==========================================
    # GET USER FACTS
    # ==========================================

    def get_memory_context(
        self
    ):


        return self.db.get_facts()
