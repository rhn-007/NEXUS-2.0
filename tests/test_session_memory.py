import os
import tempfile
import unittest

from memory.memory_manager import MemoryManager


class SessionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.original_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        os.chdir(self.original_cwd)
        self.temp_dir.cleanup()

    def test_startup_snapshot_contains_existing_personal_facts(self):
        first = MemoryManager()
        first.process_memory("my favorite sport is badminton")
        first.db.close()

        second = MemoryManager()
        try:
            snapshot = second.facts_context()
            self.assertIn("sport: badminton", snapshot)
        finally:
            second.db.close()

    def test_newly_learned_fact_refreshes_the_session_snapshot(self):
        memory = MemoryManager()
        try:
            self.assertIsNone(memory.facts_context())

            self.assertTrue(memory.process_memory("my favorite sport is badminton"))

            snapshot = memory.facts_context()
            self.assertIn("sport: badminton", snapshot)
            self.assertIs(snapshot, memory.facts_context())
        finally:
            memory.db.close()

    def test_explicit_memory_write_refreshes_the_session_snapshot(self):
        memory = MemoryManager()
        try:
            memory.remember("favourite_food", "pizza")
            self.assertIn("favourite food: pizza", memory.facts_context())
        finally:
            memory.db.close()

    def test_refresh_reloads_authoritative_database_state(self):
        memory = MemoryManager()
        try:
            memory.process_memory("my favorite sport is badminton")
            memory.db.insert("sport", "tennis", "fact")

            memory.load_session_memory()

            self.assertIn("sport: tennis", memory.facts_context())
        finally:
            memory.db.close()


if __name__ == "__main__":
    unittest.main()
