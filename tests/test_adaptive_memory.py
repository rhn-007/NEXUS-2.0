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

        self.assertIsNone(context)

    def test_adaptive_context_uses_refreshed_session_snapshot(self):
        self.memory.process_memory("my favorite sport is badminton")
        self.assertIn(
            "sport: badminton",
            self.memory.adaptive_context("What is my favourite sport?")
        )

        self.memory.db.insert("sport", "tennis")
        self.memory.load_session_memory()

        context = self.memory.adaptive_context("What is my favourite sport?")
        self.assertIn("sport: tennis", context)
        self.assertNotIn("sport: badminton", context)

    def test_invalidation_reloads_external_database_changes(self):
        self.memory.remember("sport", "badminton")
        self.assertIn("sport: badminton", self.memory.adaptive_context("badminton"))

        self.memory.db.insert("sport", "tennis", "fact")
        self.memory.invalidate_session_memory()

        context = self.memory.adaptive_context("tennis")
        self.assertIn("sport: tennis", context)
        self.assertNotIn("sport: badminton", context)

    def test_forget_removes_only_the_requested_personal_fact(self):
        self.memory.remember("sport", "badminton")
        self.memory.remember("interest", "badminton")
        self.memory.remember("food", "pizza")

        deleted = self.memory.forget(value="badminton")

        self.assertEqual(deleted, 2)
        self.assertNotIn(
            "sport: badminton",
            self.memory.adaptive_context("badminton") or ""
        )
        self.assertIn("food: pizza", self.memory.adaptive_context("pizza"))

    def test_forget_all_personal_facts_preserves_other_memory_types(self):
        self.memory.remember("name", "Rohan")
        self.memory.db.insert("user", "Earlier conversation", "conversation")
        self.memory.db.insert_knowledge(
            topic="robotics",
            title="Robotics basics",
            content="Robotics combines sensing and control."
        )

        deleted = self.memory.forget()

        self.assertEqual(deleted, 1)
        self.assertEqual(self.memory.db.get_facts(), [])
        self.assertTrue(self.memory.db.get_conversations())
        self.assertTrue(self.memory.db.search_knowledge("robotics"))

    def test_forgetting_personal_facts_preserves_episodic_memory(self):
        from core.conversation import ConversationManager
        conversation = ConversationManager()
        self.addCleanup(conversation.close)
        conversation.add_user_message("We discussed a robotics project.")
        conversation.add_assistant_message("We discussed sensors.")
        conversation.save_summary("Archived robotics discussion.")
        self.memory.remember("name", "Rohan")

        self.memory.forget()

        self.assertEqual(self.memory.db.get_facts(), [])
        self.assertEqual(
            [item["content"] for item in conversation.get_recent_transcript()],
            ["We discussed a robotics project.", "We discussed sensors."]
        )
        self.assertEqual(conversation.get_summary(), "Archived robotics discussion.")

    def test_saved_conversation_summary_is_included_in_memory_context(self):
        context = self.memory.adaptive_context(
            "What did we decide?",
            summary="We discussed the NEXUS memory redesign and its next steps."
        )
        self.assertIn("Previous conversation summary", context)
        self.assertIn("NEXUS memory redesign", context)

    def test_compatibility_context_includes_persisted_conversation_summary(self):
        from core.conversation import ConversationManager
        conversation = ConversationManager()
        self.addCleanup(conversation.close)
        conversation.save_summary("Archived memory integration test.")
        self.assertEqual(
            self.memory.get_context()["conversation_summary"],
            "Archived memory integration test."
        )

    def test_compatibility_context_uses_latest_single_value_fact(self):
        self.memory.remember("sport", "badminton")
        self.memory.remember("sport", "tennis")
        context = self.memory.get_context()
        self.assertIn(("sport", "tennis"), context["facts"])
        self.assertNotIn(("sport", "badminton"), context["facts"])

    def test_long_summary_keeps_its_most_recent_information(self):
        summary = ("Old archived detail. " * 100) + "LATEST IMPORTANT DECISION"
        context = self.memory.adaptive_context(
            "unrelated question",
            summary=summary,
            max_chars=700
        )
        self.assertIn("LATEST IMPORTANT DECISION", context)
        self.assertLessEqual(len(context), 700)

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
