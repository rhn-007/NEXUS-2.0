import os
import sqlite3
import tempfile
import unittest

from core.conversation import ConversationManager
from memory.database import MemoryDatabase


class SQLiteTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = os.path.join(self.temp_dir.name, "transactions.db")

    def test_failed_message_write_does_not_change_in_memory_context(self):
        manager = ConversationManager(self.database_path)
        self.addCleanup(manager.close)
        manager.add_user_message("saved message")
        original_context = manager.get_context()

        manager.connection.execute("""
            CREATE TRIGGER reject_conversation_insert
            BEFORE INSERT ON conversation_messages
            BEGIN
                SELECT RAISE(ABORT, 'forced test failure');
            END
        """)
        manager.connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            manager.add_user_message("must not enter context")

        self.assertEqual(manager.get_context(), original_context)
        self.assertEqual(
            [item["content"] for item in manager.get_recent_transcript()],
            ["saved message"],
        )
        self.assertFalse(manager.connection.in_transaction)

        manager.connection.execute("DROP TRIGGER reject_conversation_insert")
        manager.connection.commit()
        manager.add_user_message("write after recovery")
        self.assertEqual(
            [item["content"] for item in manager.get_context()],
            ["saved message", "write after recovery"],
        )

    def test_failed_clear_preserves_memory_until_database_clear_succeeds(self):
        manager = ConversationManager(self.database_path)
        self.addCleanup(manager.close)
        manager.add_user_message("keep until clear commits")
        manager.save_summary("existing summary")

        manager.connection.execute("""
            CREATE TRIGGER reject_conversation_delete
            BEFORE DELETE ON conversation_messages
            BEGIN
                SELECT RAISE(ABORT, 'forced test failure');
            END
        """)
        manager.connection.commit()

        with self.assertRaises(sqlite3.IntegrityError):
            manager.clear()

        self.assertEqual(
            [item["content"] for item in manager.get_context()],
            ["keep until clear commits"],
        )
        self.assertEqual(
            [item["content"] for item in manager.get_recent_transcript()],
            ["keep until clear commits"],
        )
        self.assertEqual(manager.get_summary(), "existing summary")
        self.assertFalse(manager.connection.in_transaction)

        manager.connection.execute("DROP TRIGGER reject_conversation_delete")
        manager.connection.commit()
        manager.clear()
        self.assertEqual(manager.get_context(), [])
        self.assertEqual(manager.get_recent_transcript(), [])
        self.assertIsNone(manager.get_summary())

    def test_knowledge_duplicate_rolls_back_and_connection_recovers(self):
        database = MemoryDatabase(self.database_path)
        self.addCleanup(database.close)

        first_id = database.insert_knowledge(
            topic="transactions",
            title="First entry",
            content="unique transaction test content",
        )
        self.assertIsNotNone(first_id)

        duplicate_id = database.insert_knowledge(
            topic="transactions",
            title="Duplicate entry",
            content="unique transaction test content",
        )
        self.assertIsNone(duplicate_id)
        self.assertFalse(database.connection.in_transaction)

        next_id = database.insert_knowledge(
            topic="transactions",
            title="Second entry",
            content="different transaction test content",
        )
        self.assertIsNotNone(next_id)
        self.assertEqual(len(database.search_knowledge("transaction test")), 2)


if __name__ == "__main__":
    unittest.main()
