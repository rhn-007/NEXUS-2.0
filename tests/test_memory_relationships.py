import os
import tempfile
import unittest

from memory.memory_manager import MemoryManager


class MemoryRelationshipTests(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.memory = MemoryManager()
        self.db = self.memory.db

    def tearDown(self):
        self.db.close()
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def _fact_id(self, key, value):
        for item in self.db.get_fact_records():
            if item["key"] == key and item["value"] == value:
                return item["id"]
        self.fail(f"Missing fact: {key}={value}")

    def test_relationship_is_persisted_between_existing_facts(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "NEXUS")
        first_id = self._fact_id("interest", "robotics")
        second_id = self._fact_id("project", "NEXUS")
        relationship_id = self.memory.link_memories(
            first_id, second_id, "related_to", confidence=0.93,
            origin="explicit", evidence="The user connected robotics to NEXUS."
        )
        links = self.memory.get_memory_relationships(memory_id=first_id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["id"], relationship_id)
        self.assertEqual(links[0]["source_value"], "robotics")
        self.assertEqual(links[0]["target_value"], "NEXUS")
        self.assertEqual(links[0]["origin"], "explicit")
        self.assertAlmostEqual(links[0]["confidence"], 0.93)

    def test_duplicate_relationship_is_consolidated_and_explicit_wins(self):
        self.memory.remember("interest", "AI")
        self.memory.remember("project", "NEXUS")
        first_id = self._fact_id("interest", "AI")
        second_id = self._fact_id("project", "NEXUS")
        first = self.db.create_memory_relationship(
            first_id, second_id, "related_to", confidence=0.65, origin="inferred"
        )
        second = self.db.create_memory_relationship(
            first_id, second_id, "related_to", confidence=0.95, origin="explicit",
            evidence="The user explicitly connected these facts."
        )
        self.db.create_memory_relationship(
            first_id, second_id, "related_to", confidence=0.99,
            origin="inferred", evidence="A later inferred proposal."
        )
        links = self.memory.get_memory_relationships()
        self.assertEqual(len(links), 1)
        self.assertEqual(first, second)
        self.assertEqual(links[0]["origin"], "explicit")
        self.assertAlmostEqual(links[0]["confidence"], 0.99)
        self.assertEqual(links[0]["evidence"], "The user explicitly connected these facts.")

    def test_relationships_are_removed_when_a_fact_is_forgotten(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "NEXUS")
        first_id = self._fact_id("interest", "robotics")
        second_id = self._fact_id("project", "NEXUS")
        self.memory.link_memories(first_id, second_id, "related_to")
        self.memory.forget(key="interest", value="robotics")
        self.assertEqual(self.memory.get_memory_relationships(), [])

    def test_relationships_are_removed_when_a_fact_is_replaced(self):
        self.memory.remember("sport", "badminton")
        self.memory.remember("project", "NEXUS")
        old_id = self._fact_id("sport", "badminton")
        project_id = self._fact_id("project", "NEXUS")
        self.memory.link_memories(old_id, project_id, "related_to")
        self.db.replace_memory("sport", "badminton", "tennis")
        self.assertEqual(self.memory.get_memory_relationships(), [])
        self.assertEqual(
            [row["value"] for row in self.db.get_fact_records() if row["key"] == "sport"],
            ["tennis"]
        )

    def test_invalid_endpoints_self_links_and_confidence_are_rejected(self):
        self.memory.remember("interest", "robotics")
        fact_id = self._fact_id("interest", "robotics")
        with self.assertRaises(ValueError):
            self.memory.link_memories(fact_id, fact_id, "related_to")
        with self.assertRaises(ValueError):
            self.memory.link_memories(99999, fact_id, "related_to")
        with self.assertRaises(ValueError):
            self.memory.link_memories(fact_id, 99999, "related_to")
        with self.assertRaises(ValueError):
            self.memory.link_memories(fact_id, fact_id + 1, "related_to", confidence=1.2)
        with self.assertRaises(ValueError):
            self.memory.link_memories(fact_id, fact_id + 1, "bad relation")

    def test_relationship_filters_validate_confidence_and_return_either_direction(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "NEXUS")
        first_id = self._fact_id("interest", "robotics")
        second_id = self._fact_id("project", "NEXUS")
        self.memory.link_memories(first_id, second_id, "related_to", confidence=0.8)
        self.assertEqual(len(self.memory.get_memory_relationships(memory_id=second_id)), 1)
        self.assertEqual(self.memory.get_memory_relationships(min_confidence=0.9), [])
        with self.assertRaises(ValueError):
            self.memory.get_memory_relationships(min_confidence=1.1)


if __name__ == "__main__":
    unittest.main()
