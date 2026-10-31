"""SQLite storage for NEXUS facts and conversation messages."""

import sqlite3
from datetime import datetime


class MemoryDatabase:
    def __init__(self, path="nexus_memory.db"):
        self.connection = sqlite3.connect(
            path,
            check_same_thread=False
        )
        self.create_tables()

    def create_tables(self):
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                type TEXT NOT NULL,
                created_at TEXT
            )
            """
        )
        self.connection.commit()

    def insert(self, key, value, memory_type="fact"):
        cursor = self.connection.execute(
            """
            INSERT INTO memories (key, value, type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (key, value, memory_type, datetime.now().isoformat())
        )
        self.connection.commit()
        return cursor.lastrowid

    def upsert_fact(self, key, value):
        """Update the latest fact for a key, or insert it if it is new."""
        if key == "interest":
            return self.insert(key, value, "fact")

        cursor = self.connection.execute(
            """
            UPDATE memories
            SET value = ?, created_at = ?
            WHERE id = (
                SELECT id
                FROM memories
                WHERE key = ? AND type = 'fact'
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            (value, datetime.now().isoformat(), key)
        )
        self.connection.commit()

        if cursor.rowcount == 0:
            return self.insert(key, value, "fact")

        return cursor.rowcount

    def search(self, keyword):
        cursor = self.connection.execute(
            """
            SELECT key, value, type
            FROM memories
            WHERE key LIKE ? OR value LIKE ?
            ORDER BY id DESC
            """,
            (f"%{keyword}%", f"%{keyword}%")
        )
        return cursor.fetchall()

    def get_facts(self):
        cursor = self.connection.execute(
            """
            SELECT key, value
            FROM memories
            WHERE type = 'fact'
            ORDER BY id DESC
            """
        )
        return cursor.fetchall()

    def get_conversations(self, limit=10):
        cursor = self.connection.execute(
            """
            SELECT key, value
            FROM memories
            WHERE type = 'conversation'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )
        return cursor.fetchall()

    def get_recent_messages(self, limit=20):
        """Return saved conversation messages in chronological order."""
        rows = self.get_conversations(limit)
        return [
            {"role": role, "content": content}
            for role, content in reversed(rows)
            if role in ("user", "assistant")
        ]

    def close(self):
        self.connection.close()
