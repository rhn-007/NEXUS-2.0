import os
import sqlite3
import tempfile
import unittest

from core.conversation import ConversationManager


class ConversationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = os.path.join(self.temp_dir.name, "conversation.db")

    def test_older_turns_are_archived_automatically(self):
        manager = ConversationManager(self.database_path, context_limit=4)
        self.addCleanup(manager.close)

        for index in range(8):
            manager.add_user_message(f"Discuss project topic number {index}")
            manager.add_assistant_message(f"We decided on project detail number {index}")

        summary = manager.get_summary()
        self.assertIsNotNone(summary)
        self.assertIn("project topic number 0", summary)
        self.assertIn("project detail number 5", summary)
        self.assertNotIn("project topic number 7", summary)
        self.assertLessEqual(len(summary), 2400)

    def test_summary_persists_across_restart_and_appears_in_memory_context(self):
        manager = ConversationManager(self.database_path, context_limit=4)
        for index in range(8):
            manager.add_user_message(f"Discuss archived topic {index}")
            manager.add_assistant_message(f"Archived response {index}")
        expected = manager.get_summary()
        manager.close()

        restored = ConversationManager(self.database_path, context_limit=4)
        self.addCleanup(restored.close)
        self.assertEqual(restored.get_summary(), expected)

    def test_manual_summary_update_does_not_reset_archive_cursor(self):
        manager = ConversationManager(self.database_path, context_limit=4)
        self.addCleanup(manager.close)
        for index in range(8):
            manager.add_user_message(f"Discuss archived topic {index}")
            manager.add_assistant_message(f"Archived response {index}")

        before = manager.connection.execute(
            "SELECT last_message_id FROM conversation_summaries "
            "WHERE conversation_id='default'"
        ).fetchone()[0]
        manager.save_summary("Manually updated summary")
        after = manager.connection.execute(
            "SELECT last_message_id FROM conversation_summaries "
            "WHERE conversation_id='default'"
        ).fetchone()[0]
        self.assertEqual(after, before)

    def test_existing_summary_table_is_migrated_without_losing_summary(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute("""
            CREATE TABLE conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        connection.execute(
            "INSERT INTO conversation_summaries "
            "(conversation_id, summary, updated_at) VALUES (?, ?, ?)",
            ("default", "Existing archived summary", "2026-01-01T00:00:00+00:00")
        )
        connection.commit()
        connection.close()

        manager = ConversationManager(self.database_path)
        self.addCleanup(manager.close)
        self.assertEqual(manager.get_summary(), "Existing archived summary")
        columns = {
            row["name"] for row in manager.connection.execute(
                "PRAGMA table_info(conversation_summaries)"
            ).fetchall()
        }
        self.assertIn("last_message_id", columns)


if __name__ == "__main__":
    unittest.main()
