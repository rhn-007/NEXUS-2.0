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
            "I tend to understand things much better when I build a project.",
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
            "What kind of learning approach works best for me?",
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


if __name__ == "__main__":
    unittest.main()
