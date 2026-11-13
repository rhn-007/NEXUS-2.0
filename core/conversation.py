"""
Persistent conversation manager for NEXUS.

Conversation messages are stored in the existing nexus_memory.db file.
Only a bounded recent window is sent to Ollama; the full transcript remains
available in SQLite. The system prompt is owned by OllamaClient so it is
not duplicated in the context list.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationManager:
    def __init__(self, database_path="nexus_memory.db",
                 conversation_id="default", context_limit=6):
        self.database_path = str(Path(database_path))
        self.conversation_id = conversation_id
        self.context_limit = max(4, int(context_limit))
        self.history = []
        self.connection = sqlite3.connect(
            self.database_path, timeout=30, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._create_schema()
        self._restore_recent_history()
        logger.info("Persistent conversation manager ready")

    def _create_schema(self):
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_messages_recent
                ON conversation_messages(conversation_id, id DESC)
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _restore_recent_history(self):
        rows = self.connection.execute("""
            SELECT role, content FROM conversation_messages
            WHERE conversation_id=?
            ORDER BY id DESC LIMIT ?
        """, (self.conversation_id, self.context_limit)).fetchall()
        self.history = [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def _add_message(self, role, message):
        if not message:
            return
        content = str(message)
        self.history.append({"role": role, "content": content})
        with self.connection:
            self.connection.execute("""
                INSERT INTO conversation_messages
                (conversation_id,role,content,created_at)
                VALUES (?,?,?,?)
            """, (self.conversation_id, role, content, self._now()))
        # Bound RAM use while preserving the complete transcript in SQLite.
        self.history = self.history[-self.context_limit:]

    def add_user_message(self, message):
        self._add_message("user", message)

    def add_assistant_message(self, message):
        self._add_message("assistant", message)

    def get_context(self):
        return list(self.history[-self.context_limit:])

    def get_recent_transcript(self, limit=50):
        rows = self.connection.execute("""
            SELECT role, content, created_at FROM conversation_messages
            WHERE conversation_id=?
            ORDER BY id DESC LIMIT ?
        """, (self.conversation_id, max(1, int(limit)))).fetchall()
        return [dict(row) for row in reversed(rows)]

    def save_summary(self, summary):
        with self.connection:
            self.connection.execute("""
                INSERT INTO conversation_summaries
                (conversation_id,summary,updated_at)
                VALUES (?,?,?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    summary=excluded.summary, updated_at=excluded.updated_at
            """, (self.conversation_id, summary, self._now()))

    def get_summary(self):
        row = self.connection.execute("""
            SELECT summary FROM conversation_summaries
            WHERE conversation_id=?
        """, (self.conversation_id,)).fetchone()
        return row["summary"] if row else None

    def clear(self):
        self.history.clear()
        with self.connection:
            self.connection.execute("""
                DELETE FROM conversation_messages WHERE conversation_id=?
            """, (self.conversation_id,))
            self.connection.execute("""
                DELETE FROM conversation_summaries WHERE conversation_id=?
            """, (self.conversation_id,))

    def close(self):
        self.connection.close()
