"""Read-only access to the data NEXUS already stores, for the workspaces.

Opens its own short-lived SQLite connection with writes disabled, so the
desktop UI can never change memory, research or knowledge records. Every
function returns None when the database or a table is not available yet, and a
list (possibly empty) when it is.
"""

import os
import sqlite3

from core.config import Config


def database_path():
    return os.path.abspath(Config.MEMORY_DB)


def _query(sql, params=()):

    path = database_path()

    if not os.path.exists(path):
        return None

    connection = None

    try:

        connection = sqlite3.connect(path, timeout=2.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")

        return [dict(row) for row in connection.execute(sql, params).fetchall()]

    except sqlite3.Error:

        return None

    finally:

        if connection is not None:
            connection.close()


def memory_facts(limit=300):
    return _query(
        "SELECT key, value, created_at FROM memories "
        "WHERE type = 'fact' ORDER BY id DESC LIMIT ?", (limit,))


def conversation_count():
    rows = _query("SELECT COUNT(*) AS n FROM memories WHERE type = 'conversation'")
    return rows[0]["n"] if rows else None


def knowledge_entries(limit=200):
    return _query(
        "SELECT topic, title, confidence, verification_status, learned_at "
        "FROM knowledge ORDER BY id DESC LIMIT ?", (limit,))


def research_sessions(limit=60):
    return _query(
        "SELECT s.id, s.topic, s.original_query, s.status, s.summary, "
        "s.created_at, s.completed_at, "
        "(SELECT COUNT(*) FROM research_sources r WHERE r.session_id = s.id) "
        "AS sources FROM research_sessions s ORDER BY s.id DESC LIMIT ?", (limit,))


def research_sources(session_id, limit=12):
    return _query(
        "SELECT title, publisher, url FROM research_sources "
        "WHERE session_id = ? ORDER BY id LIMIT ?", (session_id, limit))


def research_findings(session_id, limit=10):
    return _query(
        "SELECT claim FROM research_findings WHERE session_id = ? "
        "ORDER BY id LIMIT ?", (session_id, limit))


def monitored_topics():
    return _query(
        "SELECT topic, approved, enabled, cadence_days FROM monitored_topics "
        "ORDER BY id DESC")


def summary_counts():
    """Totals for the memory workspace header; missing tables count as None."""

    def count(sql):
        rows = _query(sql)
        return rows[0]["n"] if rows else None

    return {
        "facts": count("SELECT COUNT(*) AS n FROM memories WHERE type = 'fact'"),
        "conversations": count(
            "SELECT COUNT(*) AS n FROM memories WHERE type = 'conversation'"),
        "knowledge": count("SELECT COUNT(*) AS n FROM knowledge"),
        "research": count("SELECT COUNT(*) AS n FROM research_sessions"),
    }
