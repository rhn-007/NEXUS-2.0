import unittest

from memory.semantic_processor import SemanticMemoryProcessor


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_response(self, message, context=None):
        self.calls.append({"message": message, "context": context})
        if not self.responses:
            raise AssertionError("Unexpected model call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class SemanticExtractionTests(unittest.TestCase):
    def test_extracts_a_personal_fact_from_natural_wording(self):
        llm = FakeLLM([
            '{"memories":[{"key":"learning_preference",'
            '"value":"learns best through practical projects",'
            '"confidence":0.94}]}'
        ])
        processor = SemanticMemoryProcessor(llm)

        result = processor.extract(
            "I understand concepts much better when I build practical projects rather than just reading about them.",
            existing_memories=[]
        )

        self.assertEqual(
            result,
            [{
                "key": "learning_preference",
                "value": "learns best through practical projects"
            }]
        )
        self.assertEqual(len(llm.calls), 1)

    def test_extract_does_not_store_low_confidence_or_invalid_items(self):
        llm = FakeLLM([
            '{"memories":['
            '{"key":"preference","value":"maybe likes coffee","confidence":0.4},'
            '{"key":"","value":"invalid","confidence":0.99},'
            '{"key":"interest","value":"robotics","confidence":0.99}'
            ']}'
        ])
        processor = SemanticMemoryProcessor(llm)

        result = processor.extract(
            "I have recently become interested in robotics.",
            existing_memories=[]
        )

        self.assertEqual(
            result,
            [{"key": "interest", "value": "robotics"}]
        )

    def test_only_accepts_a_correction_that_matches_an_existing_memory(self):
        llm = FakeLLM([
            '{"memories":['
            '{"key":"preference","value":"detailed explanations",'
            '"replaces":"concise explanations","confidence":0.98},'
            '{"key":"interest","value":"robotics","replaces":"football",'
            '"confidence":0.98}'
            ']}'
        ])
        processor = SemanticMemoryProcessor(llm)

        result = processor.extract(
            "My explanation preference has changed, and I am interested in robotics.",
            existing_memories=[
                {"key": "preference", "value": "concise explanations"}
            ]
        )

        self.assertEqual(
            result,
            [{
                "key": "preference",
                "value": "detailed explanations",
                "replaces": "concise explanations"
            }, {
                "key": "interest",
                "value": "robotics"
            }]
        )

    def test_tool_requests_do_not_trigger_extraction(self):
        for text in (
            "I want to open Calculator and check something.",
            "I need to open Calculator and check something."
        ):
            with self.subTest(text=text):
                self.assertFalse(
                    SemanticMemoryProcessor.is_extraction_candidate(text)
                )

    def test_short_personal_statements_can_be_semantically_extracted(self):
        self.assertTrue(
            SemanticMemoryProcessor.is_extraction_candidate(
                "I study computer science."
            )
        )

    def test_explicit_remember_request_triggers_extraction(self):
        self.assertTrue(
            SemanticMemoryProcessor.is_extraction_candidate(
                "Please remember that I work best with visual examples."
            )
        )
        self.assertFalse(
            SemanticMemoryProcessor.is_extraction_candidate(
                "I don't remember my password."
            )
        )

    def test_ordinary_questions_do_not_trigger_extraction(self):
        llm = FakeLLM([])
        processor = SemanticMemoryProcessor(llm)

        self.assertEqual(
            processor.extract("What is the difference between RAM and ROM?"),
            []
        )
        self.assertEqual(llm.calls, [])

    def test_model_failure_returns_no_memories(self):
        llm = FakeLLM([RuntimeError("Ollama unavailable")])
        processor = SemanticMemoryProcessor(llm)

        result = processor.extract(
            "I usually learn best by building small projects.",
            existing_memories=[]
        )

        self.assertEqual(result, [])


class ConversationSummaryTests(unittest.TestCase):
    def test_summarizes_the_main_topic_without_replaying_messages(self):
        expected = (
            "We were discussing your preference for learning through practical "
            "projects rather than just reading about concepts."
        )
        llm = FakeLLM([expected])
        processor = SemanticMemoryProcessor(llm)

        result = processor.summarize_conversation([
            ("user", "I understand concepts much better when I build practical projects."),
            ("assistant", "That is a project-based way of learning."),
        ])

        self.assertEqual(result, expected)
        self.assertEqual(len(llm.calls), 1)
        self.assertIn("main subject", llm.calls[0]["context"][0]["content"].lower())

    def test_summary_fails_safely_when_model_returns_transcript_labels(self):
        llm = FakeLLM(["You asked about learning. I replied with some ideas."])
        processor = SemanticMemoryProcessor(llm)

        result = processor.summarize_conversation([
            ("user", "How do I learn concepts?"),
            ("assistant", "Build projects."),
        ])

        self.assertIsNone(result)

    def test_summary_does_not_call_model_without_a_model_or_messages(self):
        processor = SemanticMemoryProcessor()
        self.assertIsNone(processor.summarize_conversation([]))
        self.assertIsNone(processor.summarize_conversation([("user", "Hello")]))


class SemanticRetrievalTests(unittest.TestCase):
    def test_selects_only_existing_memory_indices_returned_by_the_model(self):
        llm = FakeLLM(['{"relevant":[2,0,99,2,"1"]}'])
        processor = SemanticMemoryProcessor(llm)
        memories = [
            {"key": "interest", "value": "drawing"},
            {"key": "project", "value": "NEXUS"},
            {"key": "learning_preference", "value": "practical projects"}
        ]

        result = processor.select_relevant(
            "What learning approach works best for me?",
            memories
        )

        self.assertEqual(result, [memories[2], memories[0]])
        self.assertEqual(len(llm.calls), 1)

    def test_non_memory_queries_do_not_trigger_semantic_retrieval(self):
        llm = FakeLLM([])
        processor = SemanticMemoryProcessor(llm)

        self.assertEqual(
            processor.select_relevant(
                "Explain how a binary search works.",
                [{"key": "interest", "value": "drawing"}]
            ),
            []
        )
        self.assertEqual(llm.calls, [])

    def test_empty_candidate_list_does_not_call_the_model(self):
        llm = FakeLLM([])
        processor = SemanticMemoryProcessor(llm)

        self.assertEqual(
            processor.select_relevant("What do I enjoy doing?", []),
            []
        )
        self.assertEqual(llm.calls, [])

    def test_model_failure_does_not_break_memory_retrieval(self):
        llm = FakeLLM([RuntimeError("Ollama unavailable")])
        processor = SemanticMemoryProcessor(llm)

        self.assertEqual(
            processor.select_relevant(
                "What am I interested in?",
                [{"key": "interest", "value": "robotics"}]
            ),
            []
        )


class SemanticMemoryManagerIntegrationTests(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile

        self.old_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        import os

        if hasattr(self, "memory"):
            self.memory.db.close()
        if hasattr(self, "conversation"):
            self.conversation.close()
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_learning_preference_is_saved_and_directly_recalled_end_to_end(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([
            '{"memories":[{"key":"learning_preference",'
            '"value":"learns best through practical projects",'
            '"confidence":0.94}]}'
        ])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)

        self.assertTrue(
            self.memory.process_memory(
                "I understand concepts much better when I build practical projects rather than just reading about them."
            )
        )
        self.assertEqual(
            self.memory.answer_fact_question(
                "What did I say about how I prefer to learn new concepts?"
            ),
            "You said you understand concepts much better by building "
            "practical projects rather than just reading about them."
        )
        # The deterministic detector handles this known preference without Ollama.
        self.assertEqual(len(llm.calls), 0)

    def test_manager_saves_a_fact_extracted_from_natural_wording(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([
            '{"memories":[{"key":"learning_preference",'
            '"value":"learns best through practical projects",'
            '"confidence":0.94}]}'
        ])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)

        self.assertTrue(
            self.memory.process_memory(
                "I tend to understand things much better when I build a project."
            )
        )
        self.assertIn(
            ("learning_preference", "learns best through practical projects"),
            [tuple(row) for row in self.memory.db.get_facts()]
        )

    def test_semantic_correction_removes_old_value_even_if_new_value_exists(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([
            '{"memories":[{"key":"preference",'
            '"value":"detailed explanations",'
            '"replaces":"concise explanations","confidence":0.98}]}'
        ])
        self.memory = MemoryManager()
        self.memory.remember("preference", "concise explanations")
        self.memory.remember("preference", "detailed explanations")
        self.memory.set_llm(llm)

        self.assertTrue(
            self.memory.process_memory(
                "My preferred explanation style has changed."
            )
        )
        preferences = [
            value for key, value in self.memory.db.get_facts()
            if key == "preference"
        ]
        self.assertNotIn("concise explanations", preferences)
        self.assertEqual(preferences.count("detailed explanations"), 1)

    def test_paraphrased_memory_query_uses_local_fallback_without_ollama(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.remember("interest", "drawing")
        self.memory.remember(
            "learning_preference",
            "learns best through practical projects"
        )
        self.memory.set_llm(llm)

        context = self.memory.adaptive_context(
            "What approach suits me?"
        )

        self.assertIn(
            "learning preference: learns best through practical projects",
            context
        )
        self.assertEqual(llm.calls, [])

    def test_bm25_ranks_matching_memory_above_unrelated_memory(self):
        from memory.memory_manager import MemoryManager

        memories = [
            {"key": "interest", "value": "drawing"},
            {
                "key": "learning_preference",
                "value": "learns best through practical projects"
            },
        ]

        ranked = MemoryManager._bm25_rank(
            "What learning approach works best for me?",
            memories
        )

        self.assertTrue(ranked)
        self.assertEqual(ranked[0][1], "learning_preference")

    def test_memory_ranking_uses_local_relevance_without_extra_ollama_call(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.remember("interest", "drawing")
        self.memory.remember(
            "learning_preference",
            "learns best by building practical projects"
        )
        self.memory.set_llm(llm)

        context = self.memory.adaptive_context(
            "What learning approach works best for me?"
        )

        self.assertIn(
            "learning preference: learns best by building practical projects",
            context
        )
        self.assertEqual(llm.calls, [])


    def test_conversation_recall_builds_local_context_without_an_extra_ollama_call(self):
        from core.conversation import ConversationManager
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.conversation = ConversationManager()
        self.conversation.add_user_message("Find beginner robotics projects.")
        self.conversation.add_assistant_message(
            "I found several beginner robotics project ideas."
        )
        self.conversation.add_user_message("Show me beginner-friendly ones.")
        self.conversation.add_assistant_message(
            "Here are beginner-friendly robotics projects."
        )
        self.conversation.add_user_message("What were we just talking about?")

        context = self.memory.answer_conversation_recall(
            "What were we just talking about?"
        )

        self.assertIn("robotics", context.lower())
        self.assertEqual(llm.calls, [])

    def test_contextual_favourite_singer_answer_is_saved_and_survives_restart(self):
        from core.conversation import ConversationManager
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.set_llm(FakeLLM([]))
        self.conversation = ConversationManager()
        self.conversation.add_user_message("Who is my favorite singer?")
        self.conversation.add_assistant_message(
            "I don't have information about your favorite singer yet."
        )
        self.conversation.add_user_message("It is The Weeknd.")

        self.assertTrue(self.memory.process_memory("It is The Weeknd."))
        self.assertEqual(
            self.memory.answer_fact_question("Who is my favorite singer?"),
            "Your favourite singer is The Weeknd."
        )
        self.assertEqual(
            self.memory.answer_fact_question("Who is my favorite music artist?"),
            "Your favourite singer is The Weeknd."
        )

        # Re-open the memory manager against the same SQLite file to verify
        # that contextual extraction is durable, not just cached in RAM.
        self.memory.db.close()
        self.memory = MemoryManager()
        self.assertEqual(
            self.memory.answer_fact_question("Who is my favorite artist?"),
            "Your favourite singer is The Weeknd."
        )

    def test_explicit_favourite_music_artist_statement_is_saved_and_recalled(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()

        self.assertTrue(
            self.memory.process_memory(
                "My favorite music artist is The Weeknd."
            )
        )
        self.assertEqual(
            self.memory.answer_fact_question("Who is my favourite singer?"),
            "Your favourite singer is The Weeknd."
        )

    def test_contextual_favourite_artist_answer_uses_canonical_singer_key(self):
        from memory.detector import MemoryDetector

        detector = MemoryDetector()
        self.assertEqual(
            detector.detect_answer(
                "It's The Weeknd.",
                "Who is my favorite music artist?"
            ),
            [{"key": "singer", "value": "The Weeknd"}]
        )

    def test_tell_me_who_my_favorite_singer_is_is_answered_without_llm(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember("singer", "The Weeknd")
        self.assertEqual(
            self.memory.answer_fact_question(
                "tell me who my favorite singer is"
            ),
            "Your favourite singer is The Weeknd."
        )

    def test_indirect_favourite_music_artist_question_is_answered_without_llm(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember("singer", "The Weeknd")
        self.assertEqual(
            self.memory.answer_fact_question(
                "Can you tell me who my favorite music artist is?"
            ),
            "Your favourite singer is The Weeknd."
        )

    def test_favourite_singer_question_is_answered_without_llm(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember("singer", "The Weeknd")
        self.assertEqual(
            self.memory.answer_fact_question("Who is my favorite music artist?"),
            "Your favourite singer is The Weeknd."
        )

    def test_ordinary_assistant_queries_do_not_make_extra_model_calls(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.remember("interest", "drawing")
        self.memory.set_llm(llm)

        self.memory.process_memory("Explain binary search.")
        self.memory.adaptive_context("Explain binary search.")

        self.assertEqual(llm.calls, [])


class DeterministicDetectorRegressionTests(unittest.TestCase):
    def test_explicit_negative_interest_is_detected_as_a_retraction(self):
        from memory.detector import MemoryDetector

        memories = MemoryDetector().detect(
            "I enjoy watching The Mentalist. "
            "The Mindhunter is not one of my interests."
        )

        self.assertIn(
            {
                "key": "interest",
                "value": "The Mindhunter",
                "remove": True
            },
            memories
        )
        self.assertIn(
            {"key": "interest", "value": "watching the mentalist"},
            memories
        )

    def test_favourite_music_artist_preserves_name_and_uses_canonical_key(self):
        from memory.detector import MemoryDetector

        memories = MemoryDetector().detect(
            "My favorite music artist is The Weeknd."
        )

        self.assertIn(
            {"key": "singer", "value": "The Weeknd"},
            memories
        )


class UnifiedMemoryPipelineRegressionTests(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile

        self.old_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)

    def tearDown(self):
        import os

        if hasattr(self, "memory"):
            self.memory.db.close()
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

    def test_learning_through_projects_is_detected_without_a_second_model_call(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)

        self.assertTrue(self.memory.process_memory(
            "I prefer learning through practical projects rather than just reading."
        ))
        self.assertIn(
            ("learning_preference",
             "understands concepts better by building practical projects rather than just reading about them"),
            [tuple(row) for row in self.memory.db.get_facts()]
        )
        self.assertEqual(llm.calls, [])

    def test_live_favourite_colour_statement_is_saved_and_recalled(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.assertTrue(self.memory.process_memory("My favourite colour is blue."))
        self.assertEqual(
            self.memory.answer_fact_question("What is my favourite colour?"),
            "Your favourite color is blue."
        )
        self.assertEqual(llm.calls, [])

    def test_live_programming_language_question_is_recalled(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.assertTrue(self.memory.process_memory(
            "My favourite programming language is Python."
        ))
        self.assertEqual(
            self.memory.answer_fact_question(
                "Which programming language do I prefer?"
            ),
            "Your favourite programming language is Python."
        )
        self.assertEqual(llm.calls, [])

    def test_learning_preference_is_recalled_in_natural_wording(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.assertTrue(self.memory.process_memory(
            "I prefer learning through practical projects."
        ))
        self.assertIn(
            "practical projects",
            self.memory.answer_fact_question("How do I prefer to learn?")
        )
        self.assertEqual(llm.calls, [])

    def test_interests_question_recalls_deterministically_detected_interest(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.assertTrue(self.memory.process_memory(
            "I am interested in robotics and artificial intelligence."
        ))
        self.assertEqual(
            self.memory.answer_fact_question("What interests did I mention earlier?"),
            "You've mentioned enjoying robotics and artificial intelligence."
        )
        self.assertEqual(llm.calls, [])

    def test_interest_recall_filters_legacy_fragments_and_deduplicates(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        legacy_values = [
            ("interest", "robotics and artificial intelligence"),
            ("interest", "drawing"),
            ("interest", "to play sometimes"),
            ("interest", "to play badminton"),
            ("interest", "badminton as the favourite sport"),
            ("interest", "playing the TV show The Mentalist"),
            ("hobby", "drawing"),
        ]
        for key, value in legacy_values:
            self.memory.remember(key, value)

        before = [tuple(row) for row in self.memory.db.get_facts()]
        self.assertEqual(
            self.memory.answer_fact_question(
                "What interests did I mention earlier?"
            ),
            "You've mentioned enjoying robotics and artificial intelligence, "
            "drawing and badminton. You also mentioned the TV show The Mentalist."
        )
        # Cleanup is presentation-only: historical SQLite rows remain intact.
        self.assertEqual(
            [tuple(row) for row in self.memory.db.get_facts()],
            before
        )

    def test_explicit_tv_show_is_stored_separately_from_interests(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)

        self.assertTrue(
            self.memory.process_memory(
                "I enjoy watching the TV show The Mentalist."
            )
        )
        facts = [tuple(row) for row in self.memory.db.get_facts()]
        self.assertIn(("tv_show", "The Mentalist"), facts)
        self.assertNotIn(("interest", "watching the TV show The Mentalist"), facts)
        self.assertEqual(
            self.memory.answer_fact_question(
                "What interests did I mention earlier?"
            ),
            "You mentioned the TV show The Mentalist."
        )
        self.assertEqual(llm.calls, [])

    def test_explicit_negative_interest_removes_old_and_legacy_show_entries(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember("interest", "The Mindhunter")
        self.memory.remember("interest", "watching The Mindhunter")
        self.memory.remember("tv_show", "The Mindhunter")
        self.memory.remember("interest", "badminton")

        self.assertTrue(self.memory.process_memory(
            "I enjoy watching The Mentalist. "
            "The Mindhunter is not one of my interests."
        ))

        facts = [tuple(row) for row in self.memory.db.get_facts()]
        self.assertNotIn(("interest", "The Mindhunter"), facts)
        self.assertNotIn(("interest", "watching The Mindhunter"), facts)
        self.assertNotIn(("tv_show", "The Mindhunter"), facts)
        self.assertIn(("interest", "badminton"), facts)
        self.assertIn(("interest", "watching the mentalist"), facts)

        context = self.memory.adaptive_context(
            "What do you remember about my hobbies and interests?",
            max_chars=3200
        )
        self.assertNotIn("Mindhunter", context)
        self.assertIn("badminton", context)
        self.assertIn("mentalist", context)

    def test_tv_show_question_uses_only_explicitly_stored_titles(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.memory.remember("tv_show", "The Mentalist")

        self.assertEqual(
            self.memory.answer_fact_question(
                "What TV shows have I told you I enjoy?"
            ),
            "You told me you enjoy watching the TV show The Mentalist."
        )
        self.assertEqual(llm.calls, [])

    def test_combined_hobbies_and_interests_question_is_deterministic(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.memory.remember("interest", "robotics and artificial intelligence")
        self.memory.remember("interest", "drawing")
        self.memory.remember("tv_show", "The Mentalist")

        self.assertEqual(
            self.memory.answer_fact_question("What are my hobbies and interests?"),
            "You've mentioned enjoying robotics and artificial intelligence "
            "and drawing. You also mentioned the TV show The Mentalist."
        )
        self.assertEqual(llm.calls, [])

    def test_legacy_viewing_interests_are_normalized_and_deduplicated(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember("interest", "watching stranger things")
        self.memory.remember("interest", "watching the mentalist")
        self.memory.remember("tv_show", "the met list")
        self.memory.remember("tv_show", "the mentalist")
        self.memory.remember("interest", "badminton")
        self.memory.remember("interest", "badminton as the favourite sport")
        self.memory.remember("interest", "to play sometimes")

        answer = self.memory.answer_fact_question(
            "What do you remember about my hobbies and interests?"
        )
        self.assertIn("badminton", answer)
        self.assertIn("Stranger Things", answer)
        self.assertIn("The Mentalist", answer)
        self.assertEqual(answer.count("The Mentalist"), 1)
        self.assertNotIn("met list", answer.lower())
        self.assertNotIn("favourite sport", answer.lower())
        self.assertNotIn("sometimes", answer.lower())

    def test_remember_hobbies_and_interests_wording_is_deterministic(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.memory.remember("interest", "badminton")
        self.memory.remember("interest", "robotics and artificial intelligence")
        self.memory.remember("tv_show", "The Mentalist")

        self.assertEqual(
            self.memory.answer_fact_question(
                "What do you remember about my hobbies and interests?"
            ),
            "You've mentioned enjoying badminton and robotics and artificial intelligence. "
            "You also mentioned the TV show The Mentalist."
        )
        self.assertEqual(llm.calls, [])

    def test_natural_learning_recall_wording_is_deterministic(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)
        self.memory.remember(
            "learning_preference",
            "understands concepts better by building practical projects"
        )

        self.assertEqual(
            self.memory.answer_fact_question(
                "What do you remember about how I prefer to learn?"
            ),
            "You said you understand concepts much better by building "
            "practical projects rather than just reading about them."
        )
        self.assertEqual(llm.calls, [])

    def test_study_time_correction_replaces_the_previous_value(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.set_llm(llm)

        self.memory.process_memory("I prefer studying in the morning.")
        self.memory.process_memory("Actually, I prefer studying at night.")

        self.assertEqual(
            self.memory.answer_fact_question("What time do I prefer studying?"),
            "You prefer studying at night."
        )
        self.assertEqual(
            self.memory._facts_by_key().get("study_time"),
            ["night"]
        )
        self.assertEqual(llm.calls, [])

    def test_personal_memory_questions_are_classified_before_tool_routing(self):
        from memory.memory_manager import MemoryManager

        for question in (
            "What do you know about my learning preferences?",
            "What do you remember about my favourite singer?",
            "What have we discussed recently?",
            "How do I prefer to learn?",
            "Who is my favourite music artist?",
        ):
            with self.subTest(question=question):
                self.assertTrue(MemoryManager.is_memory_request(question))

    def test_memory_request_context_includes_all_personal_facts(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember(
            "learning_preference",
            "understands concepts better by building practical projects"
        )
        self.memory.remember("study_time", "night")
        self.memory.remember("interest", "robotics")

        context = self.memory.adaptive_context(
            "What do you know about my learning preferences?",
            max_chars=3200
        )

        self.assertIn("learning preference:", context.lower())
        self.assertIn("study time:", context.lower())
        self.assertIn("interest:", context.lower())

    def test_learning_preference_recall_is_not_misclassified_as_a_favourite(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember(
            "learning_preference",
            "understands concepts better by building practical projects"
        )

        self.assertEqual(
            self.memory.answer_fact_question(
                "What do you know about my learning preferences?"
            ),
            "You said you understand concepts much better by building "
            "practical projects rather than just reading about them."
        )

    def test_remembered_favourite_question_uses_saved_fact(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        self.memory.remember("singer", "The Weeknd")

        self.assertEqual(
            self.memory.answer_fact_question(
                "What do you remember about my favourite singer?"
            ),
            "Your favourite singer is The Weeknd."
        )

    def test_relevant_earlier_exchange_is_added_to_shared_context(self):
        from memory.memory_manager import MemoryManager

        self.memory = MemoryManager()
        query = "What do you remember about my favourite singer?"
        context = self.memory.adaptive_context(
            query,
            recent_messages=[{"role": "user", "content": query}],
            transcript=[
                {"role": "user", "content": "Who is my favourite singer?"},
                {"role": "assistant", "content": "Your favourite singer is The Weeknd."},
            ],
            max_chars=3200
        )

        self.assertIn("Earlier exchange", context)
        self.assertIn("The Weeknd", context)


if __name__ == "__main__":
    unittest.main()
