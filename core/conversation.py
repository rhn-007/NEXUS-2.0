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

from utils.sqlite import connect_database

from utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationManager:
    def __init__(self, database_path="nexus_memory.db",
                 conversation_id="default", context_limit=6):
        self.database_path = str(Path(database_path))
        self.conversation_id = conversation_id
        self.context_limit = max(4, int(context_limit))
        self.history = []
        self.connection = connect_database(self.database_path)
        self.connection.row_factory = sqlite3.Row
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
            columns = {
                row["name"] for row in self.connection.execute(
                    "PRAGMA table_info(conversation_summaries)"
                ).fetchall()
            }
            if "last_message_id" not in columns:
                self.connection.execute(
                    "ALTER TABLE conversation_summaries "
                    "ADD COLUMN last_message_id INTEGER NOT NULL DEFAULT 0"
                )

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

        # Persist first. If SQLite rejects the write, in-memory context must
        # remain unchanged rather than containing an unsaved message.
        with self.connection:
            self.connection.execute("""
                INSERT INTO conversation_messages
                (conversation_id,role,content,created_at)
                VALUES (?,?,?,?)
            """, (self.conversation_id, role, content, self._now()))

        self.history.append({"role": role, "content": content})
        # Bound RAM use while preserving the complete transcript in SQLite.
        self.history = self.history[-self.context_limit:]

        # Compact older turns into a rolling, extractive digest. This avoids
        # another Ollama call (and its latency) while keeping long sessions
        # retrievable after their messages leave the recent context window.
        if role == "assistant":
            try:
                self._refresh_summary_if_needed()
            except sqlite3.Error as error:
                logger.warning("Could not refresh conversation summary: %s", error)

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

    def save_summary(self, summary, last_message_id=None):
        with self.connection:
            self.connection.execute("""
                INSERT INTO conversation_summaries
                (conversation_id,summary,updated_at,last_message_id)
                VALUES (?,?,?,?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    summary=excluded.summary,
                    updated_at=excluded.updated_at,
                    last_message_id=CASE
                        WHEN excluded.last_message_id=0
                        THEN conversation_summaries.last_message_id
                        ELSE excluded.last_message_id
                    END
            """, (
                self.conversation_id,
                str(summary or "").strip(),
                self._now(),
                max(0, int(last_message_id or 0))
            ))

    @staticmethod
    def _summary_excerpt(text, limit=180):
        """Create a readable, bounded excerpt without changing stored messages."""
        value = " ".join(str(text or "").split())
        if len(value) <= limit:
            return value
        shortened = value[:limit].rsplit(" ", 1)[0].rstrip()
        return shortened + "…"

    def _refresh_summary_if_needed(self, interval=12):
        state = self.connection.execute("""
            SELECT summary, last_message_id
            FROM conversation_summaries
            WHERE conversation_id=?
        """, (self.conversation_id,)).fetchone()
        previous_summary = state["summary"] if state else ""
        last_summarized_id = int(state["last_message_id"] or 0) if state else 0

        latest = self.connection.execute("""
            SELECT id FROM conversation_messages
            WHERE conversation_id=?
            ORDER BY id DESC LIMIT 1
        """, (self.conversation_id,)).fetchone()
        if not latest:
            return False
        # Leave the active context window out of the archive digest.
        cutoff = self.connection.execute("""
            SELECT id FROM conversation_messages
            WHERE conversation_id=?
            ORDER BY id DESC LIMIT 1 OFFSET ?
        """, (self.conversation_id, self.context_limit - 1)).fetchone()
        if not cutoff:
            return False
        cutoff_id = int(cutoff["id"])

        pending_count = self.connection.execute("""
            SELECT COUNT(*) FROM conversation_messages
            WHERE conversation_id=? AND id>? AND id<?
        """, (self.conversation_id, last_summarized_id, cutoff_id)).fetchone()[0]
        if pending_count < interval:
            return False

        rows = self.connection.execute("""
            SELECT id, role, content FROM conversation_messages
            WHERE conversation_id=? AND id>? AND id<?
            ORDER BY id ASC
        """, (self.conversation_id, last_summarized_id, cutoff_id)).fetchall()

        excerpts = []
        pending_user = None
        for row in rows:
            if row["role"] == "user":
                pending_user = row["content"]
            elif row["role"] == "assistant":
                if pending_user:
                    excerpts.append(
                        "User: " + self._summary_excerpt(pending_user)
                        + " | NEXUS: " + self._summary_excerpt(row["content"])
                    )
                pending_user = None

        if not excerpts:
            return False

        combined = "\n".join(part for part in (previous_summary, *excerpts) if part)
        # Keep complete exchange lines and retain the most recent archive.
        summary_lines = combined.splitlines()
        while summary_lines and len("\n".join(summary_lines)) > 2400:
            summary_lines.pop(0)
        combined = "\n".join(summary_lines)
        self.save_summary(combined, last_message_id=max(int(row["id"]) for row in rows))
        return True

    def get_summary(self):
        row = self.connection.execute("""
            SELECT summary FROM conversation_summaries
            WHERE conversation_id=?
        """, (self.conversation_id,)).fetchone()
        return row["summary"] if row else None

    def clear(self):
        # Clear RAM only after both persistent deletes have committed.
        with self.connection:
            self.connection.execute("""
                DELETE FROM conversation_messages WHERE conversation_id=?
            """, (self.conversation_id,))
            self.connection.execute("""
                DELETE FROM conversation_summaries WHERE conversation_id=?
            """, (self.conversation_id,))
        self.history.clear()

    def close(self):
        self.connection.close()
