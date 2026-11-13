"""
NEXUS Action History

A record of what NEXUS did on the computer: what was asked, which action
ran, what the tool reported, and when. It answers "did that work?" and
"what have you opened?". It keeps what the tool REPORTED; NEXUS cannot see
the screen, so it cannot prove a window really appeared.
"""

import re
import sqlite3
from datetime import datetime

from utils.logger import setup_logger


logger = setup_logger(__name__)


MAX_REQUEST_CHARS = 200
MAX_MESSAGE_CHARS = 300

# Never keep a meeting code.
_MEET_CODE = re.compile(r"\b[a-z]{3}-[a-z]{4}-[a-z]{3}\b", re.IGNORECASE)
_PRIVATE_ACTIONS = {"join_meeting": "join a Google Meet"}

_LAST = re.compile(
    r"\bdid (?:that|it|this|the last (?:one|action|command|thing)) "
    r"(?:work|succeed|go through|go ok|go okay|go well|open|run)\b"
    r"|\b(?:was|is) (?:that|it) (?:successful|done|ok|okay)\b"
    r"|\bdid you (?:do|open|launch|start|run) (?:it|that)\b"
    r"|\bwhat did you just (?:do|open|run)\b"
    r"|\bwhat was the last (?:thing|action|command)\b"
    r"|\blast action\b"
)

_ALL = re.compile(
    r"\bdid (?:those|they|all of (?:them|those)) (?:work|succeed|open|run|go through)\b"
    r"|\bwhat (?:have you|did you|all did you) (?:open|opened|done|launched|started|run)\b"
    r"|\bwhat (?:did you|have you) do(?:ne)? (?:earlier|today|so far|before)\b"
    r"|\b(?:action|command) (?:history|log)\b"
    r"|\bshow (?:me )?(?:what you(?:'ve| have) done|your actions)\b"
)


def _clean(text, limit):

    return " ".join(str(text or "").split())[:limit]


def _time(stamp):

    try:

        moment = datetime.fromisoformat(stamp)

        shown = moment.strftime("%I:%M %p").lstrip("0")

        if moment.date() != datetime.now().date():
            shown = f"{moment.strftime('%d %b')} {shown}"

        return shown

    except Exception:
        return "earlier"


class ActionHistory:

    def __init__(self, database_path="nexus_memory.db", keep=500):

        self.keep = keep

        self.connection = sqlite3.connect(
            database_path,
            check_same_thread=False,
            timeout=5
        )

        self.connection.row_factory = sqlite3.Row

        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS action_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    request TEXT NOT NULL,
                    action TEXT NOT NULL,
                    command TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    message TEXT NOT NULL
                )
            """)

    # ------------------------------------------------------
    # WRITE
    # ------------------------------------------------------

    def record(self, request, action, command, success, message=""):
        """Keep one action. Never raises: history must not break a command."""

        try:

            if action in _PRIVATE_ACTIONS:
                request = _PRIVATE_ACTIONS[action]
                command = _PRIVATE_ACTIONS[action]

            request = _MEET_CODE.sub("[meeting code]", str(request or ""))
            command = _MEET_CODE.sub("[meeting code]", str(command or ""))
            message = _MEET_CODE.sub("[meeting code]", str(message or ""))

            with self.connection:

                self.connection.execute(
                    """
                    INSERT INTO action_history
                    (created_at, request, action, command, success, message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        _clean(request, MAX_REQUEST_CHARS),
                        _clean(action, 40),
                        _clean(command, MAX_REQUEST_CHARS),
                        1 if success else 0,
                        _clean(message, MAX_MESSAGE_CHARS)
                    )
                )

                self.connection.execute(
                    "DELETE FROM action_history WHERE id <= "
                    "(SELECT MAX(id) FROM action_history) - ?",
                    (self.keep,)
                )

        except Exception as error:
            logger.warning("Could not record the action: %s", error)

    # ------------------------------------------------------
    # READ
    # ------------------------------------------------------

    def recent(self, limit=5):
        """Newest first."""

        rows = self.connection.execute(
            "SELECT * FROM action_history ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),)
        ).fetchall()

        return [dict(row) for row in rows]

    # ------------------------------------------------------
    # ANSWERS
    # ------------------------------------------------------

    @staticmethod
    def _line(item):

        outcome = (
            "the tool reported success"
            if item["success"]
            else "it failed"
        )

        said = f": \"{item['message']}\"" if item["message"] else ""

        return (
            f"{_time(item['created_at'])}, \"{item['request']}\" "
            f"({outcome}{said})"
        )

    def answer(self, text):
        """
        A reply when the message asks about NEXUS's past actions, else None.
        """

        lowered = " ".join(
            re.sub(r"[?!.,]", " ", str(text or "").lower()).split()
        )

        if not lowered or len(lowered) > 100:
            return None

        if _ALL.search(lowered):

            items = self.recent(5)

            if not items:
                return "I haven't done anything on your computer yet."

            lines = [f"- {self._line(item)}" for item in items]

            return (
                "Here's what I did recently, newest first:\n"
                + "\n".join(lines)
                + "\nI only know what each tool reported. I can't see "
                "your screen."
            )

        if _LAST.search(lowered):

            items = self.recent(1)

            if not items:
                return None

            return (
                f"My last action was at {self._line(items[0])}. "
                "I only know what the tool reported. I can't see "
                "your screen."
            )

        return None

    def close(self):

        self.connection.close()
