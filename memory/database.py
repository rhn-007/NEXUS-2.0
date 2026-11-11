import sqlite3
import hashlib
from datetime import datetime


class MemoryDatabase:
    def __init__(self, path="nexus_memory.db"):
        self.connection = sqlite3.connect(
            path,
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        cursor = self.connection.cursor()

        # Existing memory table — preserved
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                type TEXT NOT NULL,
                created_at TEXT
            )
        """)

        # Stores information NEXUS learns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_url TEXT,
                source_name TEXT,
                confidence REAL DEFAULT 0.0,
                verification_status TEXT DEFAULT 'unverified',
                tags TEXT,
                content_hash TEXT UNIQUE,
                learned_at TEXT NOT NULL
            )
        """)

        # Records NEXUS's learning activities
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learning_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity TEXT NOT NULL,
                topic TEXT,
                details TEXT,
                status TEXT DEFAULT 'completed',
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_topic
            ON knowledge(topic)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_learning_history_topic
            ON learning_history(topic)
        """)

        self.connection.commit()

    # ---------------- EXISTING MEMORY METHODS ----------------

    def insert(self, key, value, memory_type="fact"):
        cursor = self.connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO memories (key, value, type, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                key,
                value,
                memory_type,
                datetime.now().isoformat()
            ))
            self.connection.commit()
        except Exception:
            # A failed write must not keep the database locked.
            self.connection.rollback()
            raise

    def search(self, keyword):
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT key, value, type
            FROM memories
            WHERE key LIKE ? OR value LIKE ?
            ORDER BY id ASC
        """, (
            f"%{keyword}%",
            f"%{keyword}%"
        ))
        return cursor.fetchall()

    def get_facts(self):
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT key, value
            FROM memories
            WHERE type='fact'
        """)
        return cursor.fetchall()

    def get_conversations(self, limit=10):
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT key, value
            FROM memories
            WHERE type='conversation'
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()

    # ---------------- KNOWLEDGE METHODS ----------------

    def insert_knowledge(
        self,
        topic,
        title,
        content,
        source_url=None,
        source_name=None,
        confidence=0.0,
        verification_status="unverified",
        tags=None
    ):
        content_hash = hashlib.sha256(
            content.strip().encode("utf-8")
        ).hexdigest()

        cursor = self.connection.cursor()

        try:
            cursor.execute("""
                INSERT INTO knowledge (
                    topic,
                    title,
                    content,
                    source_url,
                    source_name,
                    confidence,
                    verification_status,
                    tags,
                    content_hash,
                    learned_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                topic,
                title,
                content,
                source_url,
                source_name,
                confidence,
                verification_status,
                tags,
                content_hash,
                datetime.now().isoformat()
            ))

            self.connection.commit()
            return cursor.lastrowid

        except sqlite3.IntegrityError:
            self.connection.rollback()
            return None

    def search_knowledge(self, keyword, limit=20):
        cursor = self.connection.cursor()
        search_term = f"%{keyword}%"

        cursor.execute("""
            SELECT
                id,
                topic,
                title,
                content,
                source_url,
                source_name,
                confidence,
                verification_status,
                tags,
                learned_at
            FROM knowledge
            WHERE topic LIKE ?
               OR title LIKE ?
               OR content LIKE ?
               OR tags LIKE ?
            ORDER BY learned_at DESC
            LIMIT ?
        """, (
            search_term,
            search_term,
            search_term,
            search_term,
            limit
        ))

        return [dict(row) for row in cursor.fetchall()]

    def get_knowledge(self, knowledge_id):
        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT *
            FROM knowledge
            WHERE id = ?
        """, (knowledge_id,))

        result = cursor.fetchone()
        return dict(result) if result else None

    def update_knowledge_status(
        self,
        knowledge_id,
        verification_status,
        confidence=None
    ):
        try:
            cursor = self.connection.cursor()

            if confidence is None:
                cursor.execute("""
                    UPDATE knowledge
                    SET verification_status = ?
                    WHERE id = ?
                """, (
                    verification_status,
                    knowledge_id
                ))
            else:
                cursor.execute("""
                    UPDATE knowledge
                    SET verification_status = ?,
                        confidence = ?
                    WHERE id = ?
                """, (
                    verification_status,
                    confidence,
                    knowledge_id
                ))


            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        return cursor.rowcount > 0

    def get_all_knowledge(self, limit=100):
        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT *
            FROM knowledge
            ORDER BY learned_at DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    # ---------------- LEARNING HISTORY METHODS ----------------

    def record_learning_activity(
        self,
        activity,
        topic=None,
        details=None,
        status="completed"
    ):
        try:
            cursor = self.connection.cursor()

            cursor.execute("""
                INSERT INTO learning_history (
                    activity,
                    topic,
                    details,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                activity,
                topic,
                details,
                status,
                datetime.now().isoformat()
            ))


            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

        return cursor.lastrowid

    def get_learning_history(self, limit=50):
        cursor = self.connection.cursor()

        cursor.execute("""
            SELECT *
            FROM learning_history
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    # ---------------- DATABASE MANAGEMENT ----------------

    def close(self):
        self.connection.close()
