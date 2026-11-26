import os
import tempfile
import unittest

from memory.memory_manager import MemoryManager


class AssociativeMemoryTests(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.memory = MemoryManager()
        self.associative = self.memory.associative_memory
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

    def test_ordinary_question_does_not_trigger_an_extra_model_call(self):
        class FakeLLM:
            def __init__(self):
                self.calls = 0

            def generate_response(self, *args, **kwargs):
                self.calls += 1
                return "{}"

        fake_llm = FakeLLM()
        self.memory.set_llm(fake_llm)
        self.memory.process_memory("Can you explain recursion?")
        self.assertEqual(fake_llm.calls, 0)

    def test_explicit_relationship_is_discovered_from_user_wording(self):
        self.memory.remember("project", "NEXUS")
        self.memory.remember("interest", "robotics")

        created = self.associative.discover_from_statement(
            "My NEXUS project is related to robotics."
        )

        links = self.memory.get_memory_relationships()
        self.assertGreaterEqual(created, 1)
        self.assertTrue(any(item["relation_type"] == "related_to" for item in links))
        explicit = next(item for item in links if item["relation_type"] == "related_to")
        self.assertEqual(explicit["origin"], "explicit")
        self.assertGreaterEqual(explicit["confidence"], 0.9)

    def test_existing_facts_can_be_explicitly_linked_without_new_fact(self):
        self.memory.remember("project", "NEXUS")
        self.memory.remember("interest", "robotics")

        result = self.memory.process_memory(
            "My NEXUS project is related to robotics."
        )

        self.assertTrue(result)
        self.assertTrue(any(
            item["relation_type"] == "related_to"
            for item in self.memory.get_memory_relationships()
        ))

    def test_shared_descriptive_terms_create_cautious_association(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "robotics engineering")

        links = self.memory.get_memory_relationships()
        self.assertTrue(any(
            item["relation_type"] == "shares_topic"
            and item["origin"] == "inferred"
            for item in links
        ))

    def test_negative_mentions_do_not_create_relationships(self):
        self.memory.remember("tv_show", "The Mindhunter")
        self.memory.remember("interest", "robotics")

        self.associative.discover_from_statement(
            "The Mindhunter is not one of my interests; I enjoy robotics."
        )
        self.associative.discover_from_statement(
            "I enjoy robotics, but The Mindhunter isn't one of my interests."
        )

        self.assertEqual(self.memory.get_memory_relationships(), [])

    def test_recurring_theme_requires_distinct_saved_facts(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "robotics engineering")

        patterns = self.associative.get_patterns()
        robotics = [item for item in patterns if item["pattern_key"] == "theme:robotics"]

        self.assertEqual(len(robotics), 1)
        self.assertEqual(robotics[0]["evidence_count"], 2)
        self.assertEqual(len(robotics[0]["evidence_memory_ids"]), 2)

    def test_interest_cluster_is_created_only_after_multiple_facts(self):
        self.memory.remember("interest", "badminton")
        self.memory.remember("coding", "Python")
        self.memory.remember("tv_show", "The Mentalist")

        patterns = self.associative.get_patterns()
        cluster = next(
            item for item in patterns
            if item["pattern_key"] == "interest_cluster"
        )
        self.assertEqual(cluster["evidence_count"], 3)
        self.assertIn("badminton", cluster["summary"])
        self.assertIn("Python", cluster["summary"])

    def test_patterns_are_retired_when_supporting_facts_are_forgotten(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "robotics engineering")
        self.assertTrue(self.associative.get_patterns())

        self.memory.forget(key="interest", value="robotics")

        self.assertEqual(self.associative.get_patterns(), [])
        self.assertEqual(self.memory.get_memory_relationships(), [])

    def test_associations_and_patterns_enter_relevant_context(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "robotics engineering")

        context = self.memory.adaptive_context("Tell me about robotics")

        self.assertIn("Connected personal memories", context)
        self.assertIn("Recurring memory patterns", context)
        self.assertIn("robotics", context)

    def test_recurring_topics_use_user_messages_not_assistant_text(self):
        self.db.connection.execute("""
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT ''
            )
        """)
        for message in (
            "I want to learn more about robotics.",
            "My robotics project needs better sensors.",
            "Can we discuss robotics again?",
        ):
            self.db.connection.execute(
                "INSERT INTO conversation_messages (conversation_id, role, content) "
                "VALUES ('default', 'user', ?)",
                (message,)
            )
        self.db.connection.execute(
            "INSERT INTO conversation_messages (conversation_id, role, content) "
            "VALUES ('default', 'assistant', ?)",
            ("Astronomy astronomy astronomy.",)
        )
        self.db.connection.commit()

        patterns = self.associative.rebuild_patterns()
        topic = next(
            item for item in patterns
            if item["pattern_key"] == "conversation_theme:robotics"
        )
        self.assertEqual(topic["evidence_count"], 3)
        self.assertEqual(len(topic["evidence_message_ids"]), 3)
        self.assertFalse(any(
            item["pattern_key"] == "conversation_theme:astronomy"
            for item in patterns
        ))

    def test_pattern_questions_are_answered_from_saved_evidence(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "robotics engineering")

        answer = self.memory.answer_fact_question(
            "What patterns have you noticed about me?"
        )

        self.assertIsNotNone(answer)
        self.assertIn("robotics", answer.lower())

    def test_connection_questions_do_not_claim_causation(self):
        self.memory.remember("interest", "robotics")
        self.memory.remember("project", "robotics engineering")

        answer = self.memory.answer_fact_question(
            "What connections have you found between my memories?"
        )

        self.assertIn("possible connections", answer.lower())
        self.assertIn("robotics", answer.lower())

    def test_interests_and_goals_question_does_not_invent_a_link(self):
        self.memory.remember("interest", "badminton")
        self.memory.remember("goal", "study artificial intelligence")
        self.memory.remember("tv_show", "The Mentalist")
        self.memory.remember("tv_show", "The Mindhunter")

        answer = self.memory.answer_fact_question(
            "How are my interests and goals connected?"
        )

        self.assertIn("don't have a sufficiently supported connection", answer.lower())
        self.assertNotIn("Mindhunter", answer)
        self.assertNotIn("badminton and", answer.lower())

    def test_associative_insight_questions_are_marked_for_deterministic_routing(self):
        self.assertTrue(self.memory.is_associative_insight_question(
            "What patterns have you noticed about me?"
        ))
        self.assertTrue(self.memory.is_associative_insight_question(
            "How are my interests and goals connected?"
        ))
        self.assertFalse(self.memory.is_associative_insight_question(
            "Explain how neural networks work."
        ))

    def test_project_history_questions_are_recognized_as_memory_requests(self):
        self.assertTrue(self.memory.is_memory_request(
            "What projects have I actually told you that I have built or worked on?"
        ))
        self.assertTrue(self.memory.is_memory_request(
            "What do you remember about my NEXUS project?"
        ))

    def test_project_recall_uses_user_messages_matching_the_saved_project_name(self):
        self.memory.remember("project", "NEXUS")
        transcript = [
            {
                "id": 1,
                "role": "user",
                "content": "I built NEXUS as a personal AI assistant inspired by JARVIS."
            },
            {
                "id": 2,
                "role": "assistant",
                "content": "You could turn NEXUS into a badminton training application."
            },
            {
                "id": 3,
                "role": "user",
                "content": "I want NEXUS to have persistent memory for personal facts and earlier conversations."
            },
            {
                "id": 4,
                "role": "assistant",
                "content": "You should add badminton equipment integration and player analytics."
            },
            {
                "id": 5,
                "role": "user",
                "content": "I chose SQLite for memory storage and a local Ollama model for responses."
            },
            {
                "id": 6,
                "role": "user",
                "content": "I enjoy playing badminton."
            },
        ]

        context = self.memory.adaptive_context(
            "What projects have I actually told you that I have built or worked on?",
            transcript=transcript,
            summary="NEXUS might be a badminton training application.",
            max_chars=3200
        )

        self.assertIn("personal AI assistant inspired by JARVIS", context)
        self.assertIn("persistent memory for personal facts", context)
        self.assertIn("SQLite for memory storage", context)
        self.assertNotIn("badminton training application", context)
        self.assertNotIn("badminton equipment integration", context)
        self.assertNotIn("Previous conversation summary", context)
        self.assertIn("user-authored project history", context.lower())

    def test_project_recall_matches_the_saved_project_alias_without_query_overlap(self):
        self.memory.remember("project", "NEXUS")
        transcript = [
            {
                "id": 10,
                "role": "user",
                "content": "NEXUS should learn from my previous conversations and corrections."
            },
            {
                "id": 11,
                "role": "assistant",
                "content": "Perhaps build a sports prediction feature."
            }
        ]

        context = self.memory.adaptive_context(
            "What projects have I actually built or worked on?",
            transcript=transcript,
            max_chars=3200
        )

        self.assertIn("learn from my previous conversations and corrections", context)
        self.assertNotIn("sports prediction feature", context)


if __name__ == "__main__":
    unittest.main()
