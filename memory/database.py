import sqlite3
import hashlib
import json
from datetime import datetime

from utils.sqlite import connect_database


class MemoryDatabase:
    def __init__(self, path="nexus_memory.db"):
        self.connection = connect_database(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
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

        # Explicit and inferred links between personal-memory records.
        # Original facts remain authoritative and are never rewritten.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_memory_id INTEGER NOT NULL,
                target_memory_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
                origin TEXT NOT NULL DEFAULT 'inferred'
                    CHECK (origin IN ('explicit', 'inferred')),
                evidence TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (source_memory_id <> target_memory_id),
                UNIQUE (source_memory_id, target_memory_id, relation_type),
                FOREIGN KEY (source_memory_id) REFERENCES memories(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (target_memory_id) REFERENCES memories(id)
                    ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_relationships_source
            ON memory_relationships(source_memory_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_relationships_target
            ON memory_relationships(target_memory_id)
        """)

        # Evidence-backed patterns are derived from personal facts. They are
        # disposable summaries; the source facts remain authoritative.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_key TEXT NOT NULL UNIQUE,
                pattern_type TEXT NOT NULL,
                label TEXT NOT NULL,
                summary TEXT NOT NULL,
                confidence REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
                evidence_count INTEGER NOT NULL DEFAULT 0,
                evidence_memory_ids TEXT NOT NULL DEFAULT '[]',
                evidence_message_ids TEXT NOT NULL DEFAULT '[]',
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_patterns_active
            ON memory_patterns(active, confidence DESC)
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
            ORDER BY id ASC
        """)
        return cursor.fetchall()

    def get_fact_records(self, limit=500):
        """Return personal facts with stable SQLite IDs for relationship links."""
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT id, key, value, created_at
            FROM memories
            WHERE type = 'fact'
            ORDER BY id ASC
            LIMIT ?
        """, (max(1, min(int(limit), 5000)),))
        return [dict(row) for row in cursor.fetchall()]

    def create_memory_relationship(
        self, source_memory_id, target_memory_id, relation_type,
        confidence=1.0, origin="inferred", evidence=None
    ):
        """Create or strengthen a validated link between two personal facts."""
        import math
        import re

        try:
            source_id = int(source_memory_id)
            target_id = int(target_memory_id)
            score = float(confidence)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Memory IDs and confidence must be valid numbers.")

        if source_id == target_id:
            raise ValueError("A memory cannot be related to itself.")
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("Relationship confidence must be between 0 and 1.")

        relation = str(relation_type or "").strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", relation):
            raise ValueError("Relationship type must be a short snake_case label.")
        relationship_origin = str(origin or "").strip().lower()
        if relationship_origin not in {"explicit", "inferred"}:
            raise ValueError("Relationship origin must be 'explicit' or 'inferred'.")
        evidence_text = str(evidence).strip() if evidence is not None else None
        if evidence_text and len(evidence_text) > 500:
            raise ValueError("Relationship evidence cannot exceed 500 characters.")

        cursor = self.connection.cursor()
        now = datetime.now().isoformat()
        try:
            cursor.execute("""
                SELECT id FROM memories
                WHERE type = 'fact' AND id IN (?, ?)
            """, (source_id, target_id))
            valid_ids = {int(row["id"]) for row in cursor.fetchall()}
            if valid_ids != {source_id, target_id}:
                raise ValueError("Both relationship endpoints must be existing personal facts.")

            cursor.execute("""
                SELECT id, confidence, origin, evidence
                FROM memory_relationships
                WHERE source_memory_id = ? AND target_memory_id = ?
                  AND relation_type = ?
            """, (source_id, target_id, relation))
            existing = cursor.fetchone()
            if existing:
                next_origin = (
                    "explicit" if relationship_origin == "explicit"
                    or existing["origin"] == "explicit" else "inferred"
                )
                next_confidence = max(float(existing["confidence"]), score)
                next_evidence = (
                    evidence_text if relationship_origin == "explicit" and evidence_text
                    else existing["evidence"] if existing["origin"] == "explicit"
                    else evidence_text or existing["evidence"]
                )
                cursor.execute("""
                    UPDATE memory_relationships
                    SET confidence = ?, origin = ?, evidence = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    next_confidence, next_origin, next_evidence,
                    now, int(existing["id"])
                ))
                self.connection.commit()
                return int(existing["id"])

            cursor.execute("""
                INSERT INTO memory_relationships (
                    source_memory_id, target_memory_id, relation_type,
                    confidence, origin, evidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source_id, target_id, relation, score,
                relationship_origin, evidence_text, now, now
            ))
            relationship_id = int(cursor.lastrowid)
            self.connection.commit()
            return relationship_id
        except Exception:
            self.connection.rollback()
            raise

    def replace_memory_patterns(self, patterns):
        """Replace the active derived-pattern snapshot without changing facts."""
        now = datetime.now().isoformat()
        cursor = self.connection.cursor()
        try:
            cursor.execute("UPDATE memory_patterns SET active = 0, updated_at = ?", (now,))
            for item in patterns or []:
                pattern_key = str(item.get("pattern_key") or "").strip()
                pattern_type = str(item.get("pattern_type") or "").strip()
                label = str(item.get("label") or "").strip()
                summary = str(item.get("summary") or "").strip()
                confidence = float(item.get("confidence", 0.0))
                evidence_count = max(0, int(item.get("evidence_count", 0)))
                evidence_ids = item.get("evidence_memory_ids") or []
                if (
                    not pattern_key or not pattern_type or not label or not summary
                    or not 0.0 <= confidence <= 1.0 or not evidence_count
                ):
                    continue
                cursor.execute("""
                    INSERT INTO memory_patterns (
                        pattern_key, pattern_type, label, summary, confidence,
                        evidence_count, evidence_memory_ids, evidence_message_ids,
                        active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(pattern_key) DO UPDATE SET
                        pattern_type = excluded.pattern_type,
                        label = excluded.label,
                        summary = excluded.summary,
                        confidence = excluded.confidence,
                        evidence_count = excluded.evidence_count,
                        evidence_memory_ids = excluded.evidence_memory_ids,
                        active = 1,
                        updated_at = excluded.updated_at
                """, (
                    pattern_key, pattern_type, label, summary, confidence,
                    evidence_count, json.dumps(evidence_ids),
                    json.dumps(item.get("evidence_message_ids") or []), now, now
                ))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def get_memory_patterns(self, active_only=True, limit=20):
        """Return derived memory patterns with their supporting fact IDs."""
        cursor = self.connection.cursor()
        query = "SELECT * FROM memory_patterns"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY confidence DESC, evidence_count DESC, updated_at DESC LIMIT ?"
        cursor.execute(query, (max(1, min(int(limit), 100)),))
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            for field in ("evidence_memory_ids", "evidence_message_ids"):
                try:
                    item[field] = json.loads(item.get(field) or "[]")
                except (TypeError, ValueError):
                    item[field] = []
            results.append(item)
        return results

    def get_memory_relationships(self, memory_id=None, min_confidence=0.0, limit=100):
        """Return relationship edges together with their original fact records."""
        try:
            threshold = float(min_confidence)
            row_limit = max(1, min(int(limit), 500))
            selected_id = int(memory_id) if memory_id is not None else None
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Invalid relationship filter.")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Minimum confidence must be between 0 and 1.")

        query = """
            SELECT r.id, r.source_memory_id, r.target_memory_id,
                   r.relation_type, r.confidence, r.origin, r.evidence,
                   r.created_at, r.updated_at,
                   s.key AS source_key, s.value AS source_value,
                   t.key AS target_key, t.value AS target_value
            FROM memory_relationships AS r
            JOIN memories AS s ON s.id = r.source_memory_id
            JOIN memories AS t ON t.id = r.target_memory_id
            WHERE r.confidence >= ?
        """
        params = [threshold]
        if selected_id is not None:
            query += " AND (r.source_memory_id = ? OR r.target_memory_id = ?)"
            params.extend([selected_id, selected_id])
        query += " ORDER BY r.confidence DESC, r.updated_at DESC, r.id DESC LIMIT ?"
        params.append(row_limit)
        cursor = self.connection.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

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
            # Duplicate knowledge is an expected no-op. Roll back before
            # returning so the shared connection is ready for the next write.
            self.connection.rollback()
            return None
        except Exception:
            self.connection.rollback()
            raise

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

    # ---------------- MEMORY MAINTENANCE ----------------

    def delete_memories(self, key=None, value=None, memory_type="fact"):
        """
        Delete matching rows without touching semantic knowledge or other
        memory types. With no key/value, delete all rows of memory_type.
        """
        clauses = ["type = ?"]
        params = [memory_type]

        if key is not None:
            clauses.append("LOWER(key) = LOWER(?)")
            params.append(str(key).strip())

        if value is not None:
            clauses.append("LOWER(value) = LOWER(?)")
            params.append(str(value).strip())

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "DELETE FROM memories WHERE " + " AND ".join(clauses),
                tuple(params)
            )
            self.connection.commit()
            return cursor.rowcount
        except Exception:
            self.connection.rollback()
            raise

    def replace_memory(self, key, old_value, new_value, memory_type="fact"):
        """Atomically replace one exact memory value with its correction."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                DELETE FROM memories
                WHERE type = ?
                  AND LOWER(key) = LOWER(?)
                  AND LOWER(value) = LOWER(?)
                """,
                (
                    memory_type,
                    str(key).strip(),
                    str(old_value).strip()
                )
            )
            cursor.execute(
                """
                SELECT 1 FROM memories
                WHERE type = ?
                  AND LOWER(key) = LOWER(?)
                  AND LOWER(value) = LOWER(?)
                LIMIT 1
                """,
                (
                    memory_type,
                    str(key).strip(),
                    str(new_value).strip()
                )
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO memories (key, value, type, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(key).strip(),
                        str(new_value).strip(),
                        memory_type,
                        datetime.now().isoformat()
                    )
                )
            self.connection.commit()
            return True
        except Exception:
            self.connection.rollback()
            raise

    # ---------------- DATABASE MANAGEMENT ----------------

    def close(self):
        self.connection.close()
