"""Read-only access to NEXUS research records for the desktop workspace."""
import sqlite3
from pathlib import Path


class ResearchService:
    """Read research records without changing the existing research schema."""

    def __init__(self, database_path="nexus_memory.db"):
        self.database_path = Path(database_path)

    def _connect(self):
        if not self.database_path.exists():
            return None
        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            return connection
        except sqlite3.Error:
            return None

    def list_sessions(self, search=""):
        connection = self._connect()
        if connection is None:
            return []
        try:
            query = """
                SELECT id, topic, original_query, research_depth, status,
                       summary, created_at, completed_at
                FROM research_sessions
            """
            params = ()
            if search.strip():
                query += " WHERE topic LIKE ? OR original_query LIKE ? OR summary LIKE ?"
                term = "%" + search.strip() + "%"
                params = (term, term, term)
            query += " ORDER BY COALESCE(completed_at, created_at) DESC LIMIT 200"
            return [dict(row) for row in connection.execute(query, params).fetchall()]
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def get_session(self, session_id):
        connection = self._connect()
        if connection is None:
            return None
        try:
            session = connection.execute(
                "SELECT * FROM research_sessions WHERE id=?", (int(session_id),)
            ).fetchone()
            if session is None:
                return None
            result = dict(session)
            result["sources"] = [
                dict(row) for row in connection.execute(
                    """SELECT id, title, publisher, url, relevance_score,
                              credibility_label, retrieved_at
                       FROM research_sources WHERE session_id=?
                       ORDER BY relevance_score DESC, retrieved_at DESC""",
                    (int(session_id),)
                ).fetchall()
            ]
            result["findings"] = [
                dict(row) for row in connection.execute(
                    """SELECT claim, evidence, confidence, support_count
                       FROM research_findings WHERE session_id=?
                       ORDER BY confidence DESC, id""",
                    (int(session_id),)
                ).fetchall()
            ]
            return result
        except sqlite3.Error:
            return None
        finally:
            connection.close()

    def list_topic_knowledge(self, search=""):
        connection = self._connect()
        if connection is None:
            return []
        try:
            query = "SELECT display_topic, summary, updated_at FROM topic_knowledge"
            params = ()
            if search.strip():
                term = "%" + search.strip() + "%"
                query += " WHERE display_topic LIKE ? OR summary LIKE ?"
                params = (term, term)
            query += " ORDER BY updated_at DESC LIMIT 200"
            return [dict(row) for row in connection.execute(query, params).fetchall()]
        except sqlite3.Error:
            return []
        finally:
            connection.close()
