"""
Persistent task execution records for NEXUS.

This extends the existing IntentRunner without replacing its fast path,
planner, tool router, or action history. Task records make multi-step
requests inspectable after a restart and provide a safe foundation for
later goal scheduling and explicit resume support.
"""

import re
import sqlite3
import uuid
from datetime import datetime


_MEETING_CODE = re.compile(r"\b[a-z]{3}-[a-z]{4}-[a-z]{3}\b", re.IGNORECASE)
_ALLOWED_TASK_STATUSES = {
    "queued", "running", "waiting_input", "completed", "failed", "cancelled"
}
_ALLOWED_STEP_STATUSES = {"pending", "running", "completed", "failed", "skipped"}


def _clean(value, limit):
    text = " ".join(str(value or "").split())
    text = _MEETING_CODE.sub("[meeting code]", text)
    return text[:limit]


class TaskManager:
    """Stores bounded task and step history in NEXUS's existing SQLite DB."""

    def __init__(self, database_path="nexus_memory.db", keep=200):
        self.keep = max(20, int(keep))
        self.connection = sqlite3.connect(
            str(database_path),
            timeout=10,
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    @staticmethod
    def _now():
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _create_schema(self):
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS nexus_tasks (
                    task_id TEXT PRIMARY KEY,
                    request TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT
                )
            """)
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS nexus_task_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    value TEXT NOT NULL DEFAULT '',
                    command TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT NOT NULL DEFAULT '',
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(task_id, position),
                    FOREIGN KEY(task_id) REFERENCES nexus_tasks(task_id)
                        ON DELETE CASCADE
                )
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_nexus_tasks_recent
                ON nexus_tasks(created_at DESC)
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_nexus_task_steps_task
                ON nexus_task_steps(task_id, position)
            """)

    def create_task(self, request, steps):
        """Create a task and its ordered steps before any step is executed."""
        task_id = uuid.uuid4().hex
        now = self._now()
        prepared = []

        for step in steps:
            prepared.append((
                _clean(getattr(step, "action", ""), 60),
                _clean(getattr(step, "value", ""), 300),
                _clean(getattr(step, "command", ""), 400)
            ))

        if not prepared:
            raise ValueError("A task must contain at least one step.")

        with self.connection:
            self.connection.execute("""
                INSERT INTO nexus_tasks
                (task_id, request, status, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?)
            """, (task_id, _clean(request, 500), now, now))
            self.connection.executemany("""
                INSERT INTO nexus_task_steps
                (task_id, position, action, value, command)
                VALUES (?, ?, ?, ?, ?)
            """, [
                (task_id, index, action, value, command)
                for index, (action, value, command) in enumerate(prepared)
            ])
            self._prune_locked()

        return task_id

    def _prune_locked(self):
        """Keep recent history bounded; never prune active tasks."""
        self.connection.execute("""
            DELETE FROM nexus_tasks
            WHERE task_id IN (
                SELECT task_id FROM nexus_tasks
                WHERE status IN ('completed', 'failed', 'cancelled')
                ORDER BY updated_at DESC
                LIMIT -1 OFFSET ?
            )
        """, (self.keep,))

    def start_step(self, task_id, position):
        now = self._now()
        with self.connection:
            cursor = self.connection.execute("""
                UPDATE nexus_task_steps
                SET status='running', started_at=COALESCE(started_at, ?)
                WHERE task_id=? AND position=? AND status='pending'
            """, (now, task_id, int(position)))
            if cursor.rowcount:
                self.connection.execute("""
                    UPDATE nexus_tasks SET status='running', updated_at=?
                    WHERE task_id=? AND status IN ('queued', 'running')
                """, (now, task_id))
            return cursor.rowcount == 1

    def finish_step(self, task_id, position, status, result=""):
        if status not in _ALLOWED_STEP_STATUSES - {"pending", "running"}:
            raise ValueError("Invalid final step status.")
        now = self._now()
        with self.connection:
            cursor = self.connection.execute("""
                UPDATE nexus_task_steps
                SET status=?, result=?, completed_at=?
                WHERE task_id=? AND position=? AND status IN ('pending', 'running')
            """, (status, _clean(result, 1000), now, task_id, int(position)))
            if cursor.rowcount:
                self.connection.execute("""
                    UPDATE nexus_tasks SET updated_at=? WHERE task_id=?
                """, (now, task_id))
            return cursor.rowcount == 1

    def set_task_status(self, task_id, status, result=""):
        if status not in _ALLOWED_TASK_STATUSES:
            raise ValueError("Invalid task status.")
        now = self._now()
        completed_at = now if status in {
            "completed", "failed", "cancelled"
        } else None
        with self.connection:
            cursor = self.connection.execute("""
                UPDATE nexus_tasks
                SET status=?, result=?, updated_at=?,
                    completed_at=COALESCE(?, completed_at)
                WHERE task_id=?
            """, (status, _clean(result, 1500), now, completed_at, task_id))
            self._prune_locked()
            return cursor.rowcount == 1

    def skip_remaining(self, task_id, after_position):
        now = self._now()
        with self.connection:
            self.connection.execute("""
                UPDATE nexus_task_steps
                SET status='skipped', completed_at=?
                WHERE task_id=? AND position>? AND status='pending'
            """, (now, task_id, int(after_position)))
            self.connection.execute("""
                UPDATE nexus_tasks SET updated_at=? WHERE task_id=?
            """, (now, task_id))

    def complete_task(self, task_id, result=""):
        return self.set_task_status(task_id, "completed", result)

    def get_task(self, task_id):
        row = self.connection.execute("""
            SELECT * FROM nexus_tasks WHERE task_id=?
        """, (task_id,)).fetchone()
        if row is None:
            return None
        task = dict(row)
        steps = self.connection.execute("""
            SELECT position, action, value, command, status, result,
                   started_at, completed_at
            FROM nexus_task_steps
            WHERE task_id=? ORDER BY position
        """, (task_id,)).fetchall()
        task["steps"] = [dict(item) for item in steps]
        return task

    def list_tasks(self, limit=20):
        rows = self.connection.execute("""
            SELECT task_id FROM nexus_tasks
            ORDER BY created_at DESC LIMIT ?
        """, (max(1, min(int(limit), 200)),)).fetchall()
        return [self.get_task(row["task_id"]) for row in rows]

    def get_active_tasks(self):
        rows = self.connection.execute("""
            SELECT task_id FROM nexus_tasks
            WHERE status IN ('queued', 'running', 'waiting_input')
            ORDER BY created_at
        """).fetchall()
        return [self.get_task(row["task_id"]) for row in rows]

    def answer(self, text):
        """Answer explicit task-status questions without calling the language model."""
        query = " ".join(str(text or "").lower().strip(" .!?").split())

        active_queries = {
            "show active tasks",
            "show my active tasks",
            "what tasks are you working on",
            "what are you working on",
            "what is currently running",
            "show current tasks"
        }
        recent_queries = {
            "show recent tasks",
            "show task history",
            "task history",
            "what tasks have you completed",
            "what tasks have you done"
        }

        if query in active_queries:
            tasks = self.get_active_tasks()
            if not tasks:
                return "There are no active multi-step tasks recorded."
            lines = [
                f"- {task['request']} ({task['status']})"
                for task in tasks
            ]
            return "Here are the tasks still recorded as active:\\n" + "\\n".join(lines)

        if query in recent_queries:
            tasks = self.list_tasks(8)
            if not tasks:
                return "I haven't recorded any multi-step tasks yet."
            lines = []
            for task in tasks:
                result = task.get("result") or "No final result recorded."
                lines.append(
                    f"- {task['request']} — {task['status']}: {result}"
                )
            return "Recent task history, newest first:\\n" + "\\n".join(lines)

        return None

    def close(self):
        self.connection.close()
