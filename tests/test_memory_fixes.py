import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory.database import MemoryDatabase
from memory.detector import MemoryDetector


def facts(text):
    return [(m["key"], m["value"]) for m in MemoryDetector().detect(text)]


class NameDetection(unittest.TestCase):
    def test_real_names_are_kept(self):
        self.assertEqual(facts("my name is Rohan"), [("name", "rohan")])
        self.assertEqual(facts("i'm Rohan"), [("name", "rohan")])
        self.assertEqual(facts("hello I'm Sam, nice to meet you"), [("name", "sam")])

    def test_states_are_not_names(self):
        for text in ["i am tired", "i'm hungry", "i am a student", "i'm working on it",
                     "i am sorry", "i'm learning python", "i am going home"]:
            self.assertNotIn("name", [k for k, _ in facts(text)], text)

    def test_nonsense_after_my_name_is(self):
        for text in ["my name is not important", "my name is what"]:
            self.assertEqual(facts(text), [], text)

    def test_call_me_later_is_not_a_name(self):
        self.assertEqual(facts("call me later"), [])


class NotStatements(unittest.TestCase):
    def test_questions_store_nothing(self):
        for text in ["do i like pizza", "who am i", "what is python",
                     "are you working on a project?", "is my name rohan"]:
            self.assertEqual(facts(text), [], text)

    def test_forget_stores_nothing(self):
        self.assertEqual(facts("forget that i like pizza"), [])

    def test_python_is_only_stored_when_it_is_about_him(self):
        self.assertEqual(facts("what is the best python library"), [])
        self.assertEqual(facts("python is a snake"), [])
        self.assertEqual(facts("i use python for coding"), [("coding", "python")])

    def test_ordinary_statements_still_work(self):
        self.assertEqual(facts("i like pizza"), [("interest", "pizza")])
        self.assertEqual(facts("my favorite colour is blue"), [("colour", "blue")])


class FailedWritesDoNotKeepTheDatabaseLocked(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.first = MemoryDatabase(self.path)
        self.second = sqlite3.connect(self.path, timeout=0.3)

    def tearDown(self):
        self.first.close()
        self.second.close()
        self.dir.cleanup()

    def second_can_write(self):
        self.second.execute("INSERT INTO memories (key, value, type, created_at) "
                            "VALUES ('k', 'v', 'fact', 'now')")
        self.second.commit()

    def test_a_failed_insert_releases_the_lock(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.first.insert("key", None)  # value is NOT NULL
        self.second_can_write()

    def test_a_duplicate_knowledge_row_releases_the_lock(self):
        args = dict(topic="t", title="same", content="same body")
        self.first.insert_knowledge(**args)
        self.assertIsNone(self.first.insert_knowledge(**args))
        self.second_can_write()


class NoDuplicateFacts(unittest.TestCase):
    def test_the_same_fact_is_stored_once(self):
        from memory.memory_manager import MemoryManager
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            os.chdir(folder)
            try:
                manager = MemoryManager()
                self.assertTrue(manager.process_memory("i like pizza"))
                self.assertFalse(manager.process_memory("I like pizza"))
                rows = [tuple(row) for row in manager.db.get_facts()]
                self.assertEqual(rows.count(("interest", "pizza")), 1)
                manager.db.close()
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
