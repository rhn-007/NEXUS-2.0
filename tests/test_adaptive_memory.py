import os
import tempfile
import unittest

from memory.memory_manager import MemoryManager


class AdaptiveMemoryTests(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.memory = MemoryManager()

    def tearDown(self):
        self.memory.db.close()
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_core_preferences_and_relevant_facts_are_selected(self):
        self.memory.remember("name", "Rohan")
        self.memory.remember("preference", "concise explanations")
        self.memory.remember("sport", "badminton")
        self.memory.remember("food", "pizza")

        context = self.memory.adaptive_context("Tell me about badminton")

        self.assertIn("name: Rohan", context)
        self.assertIn("preference: concise explanations", context)
        self.assertIn("sport: badminton", context)
        self.assertNotIn("food: pizza", context)

    def test_relevant_past_exchange_is_retrieved(self):
        transcript = [
            {"role": "user", "content": "How do I improve at badminton?"},
            {"role": "assistant", "content": "Practice footwork and consistency."},
            {"role": "user", "content": "What is the weather today?"},
            {"role": "assistant", "content": "I would need your location."}
        ]

        context = self.memory.adaptive_context(
            "Can you remind me about badminton practice?",
            transcript=transcript
        )

        self.assertIn("Relevant past conversation memory", context)
        self.assertIn("improve at badminton", context)
        self.assertIn("Practice footwork", context)
        self.assertNotIn("weather today", context)

    def test_active_conversation_is_not_duplicated_as_episodic_memory(self):
        transcript = [
            {"role": "user", "content": "How do I improve badminton?"},
            {"role": "assistant", "content": "Practice regularly."}
        ]
        active = [{"role": "user", "content": "How do I improve badminton?"}]

        context = self.memory.adaptive_context(
            "How do I improve badminton?",
            recent_messages=active,
            transcript=transcript
        )

        self.assertNotIn("Earlier exchange", context)

    def test_adaptive_context_uses_refreshed_session_snapshot(self):
        self.memory.process_memory("my favorite sport is badminton")
        self.assertIn(
            "sport: badminton",
            self.memory.adaptive_context("What is my favourite sport?")
        )

        self.memory.db.insert("sport", "tennis", "fact")
        self.memory.load_session_memory()

        context = self.memory.adaptive_context("What is my favourite sport?")
        self.assertIn("sport: tennis", context)
        self.assertNotIn("sport: badminton", context)

    def test_context_respects_character_budget(self):
        self.memory.remember("preference", "short answers")
        self.memory.remember("interest", " ".join(["badminton"] * 80))

        context = self.memory.adaptive_context(
            "badminton",
            max_chars=180
        )

        self.assertLessEqual(len(context), 180)


if __name__ == "__main__":
    unittest.main()
