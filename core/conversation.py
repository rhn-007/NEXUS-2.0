"""Manages NEXUS conversation history and model context."""

from utils.logger import setup_logger
from ai.prompts import SYSTEM_PROMPT


logger = setup_logger(__name__)


class ConversationManager:
    def __init__(self):
        self.history = []
        logger.info("Conversation manager ready")

    def load_history(self, messages):
        """Load validated messages from persistent storage."""
        self.history = []

        for item in messages:
            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content")

            if role not in ("user", "assistant") or not content:
                continue

            self.history.append({
                "role": role,
                "content": str(content)
            })

        self.history = self.history[-20:]
        logger.info("Loaded %s messages from persistent history", len(self.history))

    def add_user_message(self, message):
        self.history.append({
            "role": "user",
            "content": message
        })
        self.history = self.history[-20:]

    def add_assistant_message(self, message):
        self.history.append({
            "role": "assistant",
            "content": message
        })
        self.history = self.history[-20:]

    def get_context(self, memory_context=""):
        system_content = SYSTEM_PROMPT.strip()

        if memory_context:
            system_content += (
                "\n\n"
                "LONG-TERM MEMORY\n"
                "-----------------\n"
                f"{memory_context}"
            )

        return [
            {
                "role": "system",
                "content": system_content
            },
            *self.history[-20:]
        ]

    def clear(self):
        self.history.clear()
