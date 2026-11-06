"""
NEXUS Personal Language Intelligence

Learns recurring spoken vocabulary and explicit wording corrections.
All profile data is stored locally in nexus_memory.db.
"""

import re
import sqlite3
from datetime import datetime, timezone


class PersonalLanguageLearner:
    STOP_WORDS = {
        "the", "and", "for", "that", "this", "with", "you", "your",
        "are", "was", "were", "have", "has", "had", "will", "would",
        "could", "should", "can", "could", "from", "about", "what",
        "when", "where", "which", "who", "why", "how", "tell", "please",
        "just", "like", "want", "need", "make", "give", "does", "doing",
        "today", "then", "than", "there", "their", "them", "they",
        "into", "onto", "also", "some", "more", "less", "much", "many",
        "very", "really", "yeah", "yes", "okay", "ok", "well", "hello",
        "hey", "uh", "um", "hmm", "right", "thing", "things", "good",
        "great", "tell", "said", "says", "mean", "means", "when", "say"
    }

    def __init__(self, database_path="nexus_memory.db"):
        self.connection = sqlite3.connect(
            database_path,
            timeout=30,
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS personal_language (
                    phrase TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    corrected_to TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_personal_language_kind_count
                ON personal_language(kind, occurrence_count DESC)
            """)

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize(value):
        return " ".join(str(value).strip().strip(" \"'.,!?;:").split())

    def _increment(self, phrase, kind):
        phrase = self._normalize(phrase)
        if not phrase or len(phrase) > 80:
            return
        with self.connection:
            self.connection.execute("""
                INSERT INTO personal_language
                    (phrase, kind, occurrence_count, updated_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(phrase) DO UPDATE SET
                    occurrence_count = personal_language.occurrence_count + 1,
                    updated_at = excluded.updated_at
            """, (phrase, kind, self._now()))

    def add_correction(self, heard_phrase, intended_phrase):
        heard = self._normalize(heard_phrase)
        intended = self._normalize(intended_phrase)
        if not heard or not intended or heard.casefold() == intended.casefold():
            return False

        with self.connection:
            self.connection.execute("""
                INSERT INTO personal_language
                    (phrase, kind, occurrence_count, corrected_to, updated_at)
                VALUES (?, 'correction', 1, ?, ?)
                ON CONFLICT(phrase) DO UPDATE SET
                    kind = 'correction',
                    corrected_to = excluded.corrected_to,
                    occurrence_count = personal_language.occurrence_count + 1,
                    updated_at = excluded.updated_at
            """, (heard, intended, self._now()))
        return True

    def _extract_explicit_correction(self, text):
        patterns = [
            # "When I say X, I mean Y" maps X to Y.
            (r"(?i)when i say (.{1,70}?), i mean (.{1,70}?)[.!?]?$", 1, 2),
            # "I said X, not Y" means the intended wording is X.
            (r"(?i)i said (.{1,70}?), not (.{1,70}?)[.!?]?$", 2, 1),
            # "X, not Y" is intentionally not inferred without "I said".
        ]
        for pattern, heard_index, intended_index in patterns:
            match = re.search(pattern, text.strip())
            if match:
                heard = self._normalize(match.group(heard_index))
                intended = self._normalize(match.group(intended_index))
                if self.add_correction(heard, intended):
                    return heard, intended
        return None

    def observe(self, text, source="voice"):
        """
        Learn vocabulary only from transcribed voice input.
        Explicit correction statements are accepted from either input mode.
        """
        correction = self._extract_explicit_correction(str(text))
        if correction:
            return correction

        if source != "voice":
            return None

        # Count meaningful words, not every conversational filler.
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", str(text))
        for token in tokens:
            normalized = token.strip(".,!?;:").lower()
            if normalized not in self.STOP_WORDS:
                self._increment(normalized, "term")

        return None

    def get_corrections(self):
        rows = self.connection.execute("""
            SELECT phrase, corrected_to
            FROM personal_language
            WHERE kind='correction' AND corrected_to IS NOT NULL
            ORDER BY occurrence_count DESC, updated_at DESC
            LIMIT 50
        """).fetchall()
        return {row["phrase"]: row["corrected_to"] for row in rows}

    def get_vocabulary(self, limit=20):
        rows = self.connection.execute("""
            SELECT phrase
            FROM personal_language
            WHERE kind='term' AND occurrence_count >= 2
            ORDER BY occurrence_count DESC, updated_at DESC
            LIMIT ?
        """, (max(1, int(limit)),)).fetchall()
        return [row["phrase"] for row in rows]

    def get_context(self):
        terms = self.get_vocabulary(15)
        corrections = self.get_corrections()
        if not terms and not corrections:
            return None

        parts = [
            "PERSONAL COMMUNICATION CONTEXT:",
            "These are patterns learned from the user's previous wording. "
            "Use them only as helpful context; do not force a correction "
            "when the current meaning is clear or different."
        ]
        if terms:
            parts.append("Frequently used vocabulary: " + ", ".join(terms))
        if corrections:
            mappings = [
                f'"{heard}" means "{intended}"'
                for heard, intended in corrections.items()
            ]
            parts.append("Explicit wording corrections: " + "; ".join(mappings))
        return "\n".join(parts)

    def get_profile_summary(self):
        terms = self.get_vocabulary(20)
        corrections = self.get_corrections()
        if not terms and not corrections:
            return (
                "I haven't learned enough recurring speech patterns yet. "
                "I'll gradually recognise vocabulary you use often and "
                "remember any corrections you explicitly teach me."
            )

        lines = ["Here's what I've learned about your communication:"]
        if terms:
            lines.append("Frequently used terms: " + ", ".join(terms))
        if corrections:
            lines.append("Your corrections:")
            lines.extend(
                f'- "{heard}" means "{intended}".'
                for heard, intended in corrections.items()
            )
        return "\n".join(lines)

    def clear_profile(self):
        with self.connection:
            self.connection.execute("DELETE FROM personal_language")

    def close(self):
        self.connection.close()
