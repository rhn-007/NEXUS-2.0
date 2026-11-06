"""
Persistent research storage for NEXUS.

This module adds research-specific tables to the existing SQLite database.
It does not alter or delete the existing memories, knowledge, or
learning_history tables.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class ResearchStore:
    def __init__(self, database_path="nexus_memory.db"):
        self.database_path = str(Path(database_path))
        self.connection = sqlite3.connect(
            self.database_path, timeout=30, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def _create_schema(self):
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS research_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    original_query TEXT NOT NULL,
                    research_depth TEXT NOT NULL DEFAULT 'adaptive',
                    status TEXT NOT NULL DEFAULT 'running',
                    summary TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS research_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    publisher TEXT,
                    published_at TEXT,
                    retrieved_at TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    relevance_score REAL NOT NULL DEFAULT 0,
                    credibility_label TEXT NOT NULL DEFAULT 'unassessed',
                    extraction_type TEXT NOT NULL DEFAULT 'webpage',
                    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
                        ON DELETE CASCADE,
                    UNIQUE(session_id, canonical_url)
                );

                CREATE TABLE IF NOT EXISTS research_findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    source_id INTEGER,
                    claim TEXT NOT NULL,
                    evidence TEXT,
                    confidence REAL NOT NULL DEFAULT 0,
                    support_count INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES research_sessions(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY(source_id) REFERENCES research_sources(id)
                        ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS topic_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_key TEXT NOT NULL UNIQUE,
                    display_topic TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    open_questions TEXT NOT NULL DEFAULT '[]',
                    last_researched_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS monitored_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL UNIQUE,
                    approved INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    cadence_days INTEGER NOT NULL DEFAULT 7,
                    last_checked_at TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_research_sessions_topic
                    ON research_sessions(topic);
                CREATE INDEX IF NOT EXISTS idx_research_sources_hash
                    ON research_sources(content_hash);
                CREATE INDEX IF NOT EXISTS idx_research_sources_publisher
                    ON research_sources(publisher);
                CREATE INDEX IF NOT EXISTS idx_research_findings_session
                    ON research_findings(session_id);
            """)

            # FTS5 is optional on SQLite builds. Fall back to LIKE retrieval
            # when the extension is unavailable.
            try:
                self.connection.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS research_source_fts
                    USING fts5(title, publisher, content, content='research_sources',
                               content_rowid='id')
                """)
                self.connection.executescript("""
                    CREATE TRIGGER IF NOT EXISTS research_sources_ai
                    AFTER INSERT ON research_sources BEGIN
                        INSERT INTO research_source_fts(rowid,title,publisher,content)
                        VALUES(new.id,new.title,coalesce(new.publisher,''),new.content);
                    END;
                    CREATE TRIGGER IF NOT EXISTS research_sources_ad
                    AFTER DELETE ON research_sources BEGIN
                        INSERT INTO research_source_fts(research_source_fts,rowid,title,publisher,content)
                        VALUES('delete',old.id,old.title,coalesce(old.publisher,''),old.content);
                    END;
                    CREATE TRIGGER IF NOT EXISTS research_sources_au
                    AFTER UPDATE ON research_sources BEGIN
                        INSERT INTO research_source_fts(research_source_fts,rowid,title,publisher,content)
                        VALUES('delete',old.id,old.title,coalesce(old.publisher,''),old.content);
                        INSERT INTO research_source_fts(rowid,title,publisher,content)
                        VALUES(new.id,new.title,coalesce(new.publisher,''),new.content);
                    END;
                """)
                self.fts_available = True
            except sqlite3.OperationalError:
                self.fts_available = False

    def create_session(self, topic, query, depth="adaptive", metadata=None):
        with self.connection:
            cursor = self.connection.execute("""
                INSERT INTO research_sessions
                (topic, original_query, research_depth, status, created_at, metadata_json)
                VALUES (?, ?, ?, 'running', ?, ?)
            """, (topic, query, depth, utc_now(),
                  json.dumps(metadata or {}, ensure_ascii=False)))
        return cursor.lastrowid

    def save_source(self, session_id, source):
        url = source["url"].strip()
        content = source["content"].strip()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        canonical = url.split("#", 1)[0].rstrip("/")
        with self.connection:
            self.connection.execute("""
                INSERT OR IGNORE INTO research_sources
                (session_id,url,canonical_url,title,publisher,published_at,
                 retrieved_at,content,content_hash,relevance_score,
                 credibility_label,extraction_type)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                session_id, url, canonical, source.get("title") or url,
                source.get("publisher") or source.get("source"),
                source.get("published_at"), utc_now(), content, digest,
                float(source.get("relevance_score", 0)),
                source.get("credibility_label", "unassessed"),
                source.get("extraction_type", "webpage")
            ))
            row = self.connection.execute("""
                SELECT id FROM research_sources
                WHERE session_id=? AND canonical_url=?
            """, (session_id, canonical)).fetchone()
        return row["id"] if row else None

    def save_finding(self, session_id, claim, evidence=None,
                     source_id=None, confidence=0.0, support_count=1):
        with self.connection:
            cursor = self.connection.execute("""
                INSERT INTO research_findings
                (session_id,source_id,claim,evidence,confidence,support_count,created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (session_id, source_id, claim, evidence,
                  max(0.0, min(1.0, float(confidence))),
                  max(1, int(support_count)), utc_now()))
        return cursor.lastrowid

    def finish_session(self, session_id, summary, status="completed",
                       metadata=None):
        with self.connection:
            self.connection.execute("""
                UPDATE research_sessions
                SET summary=?, status=?, completed_at=?,
                    metadata_json=?
                WHERE id=?
            """, (summary, status, utc_now(),
                  json.dumps(metadata or {}, ensure_ascii=False), session_id))

    def update_topic_knowledge(self, topic, summary, open_questions=None):
        key = " ".join(topic.casefold().split())
        with self.connection:
            self.connection.execute("""
                INSERT INTO topic_knowledge
                (topic_key,display_topic,summary,open_questions,last_researched_at,updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(topic_key) DO UPDATE SET
                    display_topic=excluded.display_topic,
                    summary=excluded.summary,
                    open_questions=excluded.open_questions,
                    last_researched_at=excluded.last_researched_at,
                    updated_at=excluded.updated_at
            """, (key, topic, summary,
                  json.dumps(open_questions or [], ensure_ascii=False),
                  utc_now(), utc_now()))

    def get_topic_knowledge(self, topic):
        key = " ".join(topic.casefold().split())
        row = self.connection.execute("""
            SELECT * FROM topic_knowledge WHERE topic_key=?
        """, (key,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["open_questions"] = json.loads(result["open_questions"])
        return result

    def search_sources(self, query, limit=8):
        words = [w for w in query.split() if len(w) > 2]
        if not words:
            return []
        if self.fts_available:
            expression = " OR ".join('"' + w.replace('"', '""') + '"' for w in words[:12])
            try:
                rows = self.connection.execute("""
                    SELECT s.* FROM research_source_fts f
                    JOIN research_sources s ON s.id=f.rowid
                    WHERE research_source_fts MATCH ?
                    ORDER BY bm25(research_source_fts)
                    LIMIT ?
                """, (expression, limit)).fetchall()
                return [dict(row) for row in rows]
            except sqlite3.OperationalError:
                pass
        clauses, params = [], []
        for word in words[:8]:
            clauses.append("(title LIKE ? OR content LIKE ? OR publisher LIKE ?)")
            params.extend([f"%{word}%", f"%{word}%", f"%{word}%"])
        rows = self.connection.execute(
            "SELECT * FROM research_sources WHERE " + " OR ".join(clauses) +
            " ORDER BY retrieved_at DESC LIMIT ?", (*params, limit)
        ).fetchall()
        return [dict(row) for row in rows]

    def add_monitored_topic(self, topic, cadence_days=7, approved=False):
        with self.connection:
            self.connection.execute("""
                INSERT INTO monitored_topics(topic,approved,enabled,cadence_days,created_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(topic) DO UPDATE SET
                    approved=excluded.approved, enabled=excluded.enabled,
                    cadence_days=excluded.cadence_days
            """, (topic, int(approved), int(approved),
                  max(1, int(cadence_days)), utc_now()))

    def list_monitored_topics(self):
        rows = self.connection.execute("""
            SELECT * FROM monitored_topics ORDER BY topic
        """).fetchall()
        return [dict(row) for row in rows]

    def close(self):
        self.connection.close()
