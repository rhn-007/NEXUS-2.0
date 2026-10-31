"""Coordinates memory detection, storage, retrieval, and context."""

from memory.database import MemoryDatabase
from memory.detector import MemoryDetector


class MemoryManager:
    def __init__(self):
        self.db = MemoryDatabase()
        self.detector = MemoryDetector()

    def process_memory(self, text):
        memories = self.detector.detect(text)

        if not memories:
            return False

        for memory in memories:
            self.db.upsert_fact(
                memory["key"],
                memory["value"]
            )

        return True

    def handle_memory_query(self, text):
        text = text.lower()

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

        if any(word in text for word in profile_words):
            facts = self.get_facts()

            if not facts:
                return "I haven't learned much about you yet."

            response = [
                "From what you've shared with me, here is what I know about you:",
                ""
            ]

            response.extend(
                f"• {key.replace('_', ' ').title()}: {value}"
                for key, value in facts
            )
            return "\n".join(response)

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

        if any(word in text for word in recall_words):
            chats = self.db.get_conversations(20)

            if not chats:
                return "I don't have any previous conversations stored yet."

            response = [
                "From our previous conversations, I remember:",
                ""
            ]

            for role, content in reversed(chats):
                response.append(f"{role.title()}: {content}")

            return "\n".join(response)

        return None

    def get_facts(self):
        """Return the latest value for each fact key, without old duplicates."""
        rows = self.db.get_facts()
        latest = {}
        interests = []

        for key, value in rows:
            if key == "interest":
                if value not in interests:
                    interests.append(value)
            elif key not in latest:
                latest[key] = value

        facts = list(latest.items())
        facts.extend(("interest", value) for value in interests)
        return facts

    def build_context(self):
        facts = self.get_facts()

        if not facts:
            return ""

        lines = [
            "Relevant information the user has previously shared:"
        ]
        lines.extend(
            f"- {key.replace('_', ' ')}: {value}"
            for key, value in facts
        )
        lines.append(
            "Use these details only when relevant. Do not invent additional personal facts."
        )
        return "\n".join(lines)

    def get_recent_messages(self, limit=20):
        return self.db.get_recent_messages(limit)

    def save_conversation(self, user, assistant):
        self.db.insert("user", user, "conversation")
        self.db.insert("assistant", assistant, "conversation")

    def get_context(self):
        return {
            "facts": self.get_facts(),
            "recent_conversations": self.db.get_conversations(12)
        }

    def remember(self, key, value):
        return self.db.upsert_fact(key, value)

    def recall(self, key):
        results = self.db.search(key)
        return results[0][1] if results else None

    def get_memory_context(self):
        return self.db.search("")
