"""Shared SQLite connection configuration for NEXUS."""

import sqlite3


SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000


def connect_database(database_path):
    """Open a thread-shareable connection with consistent contention handling.

    WAL is persistent for file-backed databases. Applying the pragma here also
    ensures newly introduced NEXUS database components use the same mode.
    """
    connection = sqlite3.connect(
        str(database_path),
        timeout=SQLITE_TIMEOUT_SECONDS,
        check_same_thread=False
    )
    connection.execute(
        f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}"
    )
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
