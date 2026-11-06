"""
NEXUS self-observation and performance event store.

Stores operational metadata only. It deliberately does not save raw user
messages or assistant responses.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


class PerformanceObserver:
    def __init__(self, database_path="nexus_memory.db"):
        self.database_path = str(Path(database_path))
        self.connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self):
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS nexus_observation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_nexus_observation_recent
                ON nexus_observation_events(created_at DESC)
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_nexus_observation_type_status
                ON nexus_observation_events(event_type, status)
            """)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def record_event(self, event_type, status="completed",
                     duration_ms=None, metadata=None):
        if not event_type or not str(event_type).strip():
            raise ValueError("An event type is required.")

        safe_duration = None
        if duration_ms is not None:
            safe_duration = max(0.0, float(duration_ms))

        # Metadata should contain operational measurements only, never raw
        # prompts, transcripts, credentials, or response content.
        encoded_metadata = json.dumps(
            metadata or {},
            ensure_ascii=False,
            default=str
        )

        with self.connection:
            cursor = self.connection.execute("""
                INSERT INTO nexus_observation_events
                (event_type, status, duration_ms, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                str(event_type).strip()[:80],
                str(status).strip()[:40] or "unknown",
                safe_duration,
                encoded_metadata,
                self._now()
            ))
        return cursor.lastrowid

    def get_recent_events(self, limit=100, event_type=None):
        limit = max(1, min(1000, int(limit)))
        if event_type:
            rows = self.connection.execute("""
                SELECT * FROM nexus_observation_events
                WHERE event_type=?
                ORDER BY id DESC LIMIT ?
            """, (event_type, limit)).fetchall()
        else:
            rows = self.connection.execute("""
                SELECT * FROM nexus_observation_events
                ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()

        events = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json"))
            except (TypeError, json.JSONDecodeError):
                item["metadata"] = {}
            events.append(item)
        return events

    def get_metrics(self, days=7):
        days = max(1, min(365, int(days)))
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()
        rows = self.connection.execute("""
            SELECT
                event_type,
                status,
                COUNT(*) AS event_count,
                AVG(duration_ms) AS average_duration_ms,
                MAX(duration_ms) AS maximum_duration_ms
            FROM nexus_observation_events
            WHERE created_at >= ?
            GROUP BY event_type, status
            ORDER BY event_type, status
        """, (cutoff,)).fetchall()
        return [dict(row) for row in rows]

    def get_report(self, days=7):
        metrics = self.get_metrics(days)
        if not metrics:
            return (
                "I do not have enough recorded activity to produce a "
                "performance report yet."
            )

        totals = {}
        for item in metrics:
            name = item["event_type"]
            bucket = totals.setdefault(name, {
                "events": 0,
                "completed": 0,
                "failed": 0,
                "durations": []
            })
            count = int(item["event_count"])
            bucket["events"] += count
            if item["status"] == "completed":
                bucket["completed"] += count
            elif item["status"] == "failed":
                bucket["failed"] += count
            if item["average_duration_ms"] is not None:
                bucket["durations"].append(
                    (float(item["average_duration_ms"]), count)
                )

        lines = [f"NEXUS activity report — last {days} days"]
        for name, values in sorted(totals.items()):
            line = (
                f"- {name.replace('_', ' ').title()}: "
                f"{values['events']} event(s), "
                f"{values['completed']} completed, "
                f"{values['failed']} failed"
            )
            if values["durations"]:
                count = sum(n for _, n in values["durations"])
                average = sum(
                    avg * n for avg, n in values["durations"]
                ) / count
                line += f", average {average / 1000:.2f}s"
            lines.append(line)
        lines.append(
            "This report measures recorded activity; it does not by itself "
            "prove that NEXUS has improved."
        )
        return "\n".join(lines)

    def close(self):
        self.connection.close()
