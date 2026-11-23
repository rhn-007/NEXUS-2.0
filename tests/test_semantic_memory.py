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
        os.chdir(self.old_cwd)
        self.temp_dir.cleanup()

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

    def test_manager_uses_semantic_retrieval_for_a_paraphrased_memory_query(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM(['{"relevant":[1]}'])
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
        self.assertEqual(len(llm.calls), 1)

    def test_semantic_ranking_runs_even_when_weak_lexical_overlap_exists(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM(['{"relevant":[1]}'])
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
        self.assertEqual(len(llm.calls), 1)

    def test_ordinary_assistant_queries_do_not_make_extra_model_calls(self):
        from memory.memory_manager import MemoryManager

        llm = FakeLLM([])
        self.memory = MemoryManager()
        self.memory.remember("interest", "drawing")
        self.memory.set_llm(llm)

        self.memory.process_memory("Explain binary search.")
        self.memory.adaptive_context("Explain binary search.")

        self.assertEqual(llm.calls, [])


if __name__ == "__main__":
    unittest.main()
