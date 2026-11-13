import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory.detector import MemoryDetector
from memory.memory_manager import MemoryManager


def found(text):
    return [(m["key"], m["value"]) for m in MemoryDetector().detect(text)]


class Detector(unittest.TestCase):
    def test_preferences_are_saved(self):
        for text, value in [("remember that i prefer concise explanations", "concise explanations"),
                            ("i prefer short answers", "short answers"),
                            ("keep your answers short", "answers short"),
                            ("i want shorter explanations", "shorter explanations")]:
            self.assertIn(("preference", value), found(text), text)

    def test_the_project_name_is_kept(self):
        self.assertEqual(found("i'm working on a project called Nexus"), [("project", "nexus")])
        self.assertEqual(found("im working on a project called nexus, an offline assistant"),
                         [("project", "nexus")])
        self.assertEqual(found("my project is nexus"), [("project", "nexus")])
        self.assertEqual(found("i am working on a project called my first app and it is hard"),
                         [("project", "my first app")])

    def test_no_made_up_project_when_there_is_no_name(self):
        self.assertEqual(found("i'm working on a project"), [])
        self.assertEqual(found("i am working on my project tonight"), [])

    def test_both_spellings_of_favourite(self):
        self.assertEqual(found("my favorite colour is blue"), [("colour", "blue")])
        self.assertEqual(found("my favourite programming language is python"),
                         [("programming_language", "python")])

    def test_questions_about_preferences_store_nothing(self):
        self.assertEqual(found("what do i prefer"), [])


class WithMemory(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        os.chdir(self.dir.name)
        self.memory = MemoryManager()
        for text in ["my name is rohan", "my favourite programming language is python",
                     "i'm working on a project called Nexus", "i prefer concise explanations",
                     "i prefer short answers", "my favorite food is pizza"]:
            self.memory.process_memory(text)

    def tearDown(self):
        self.memory.db.close()
        os.chdir(self.old)
        self.dir.cleanup()

    def ask(self, text):
        return self.memory.answer_fact_question(text)


class Answers(WithMemory):
    def test_name(self):
        self.assertEqual(self.ask("what is my name"), "Your name is Rohan.")
        self.assertEqual(self.ask("hey nexus, what's my name?"), "Your name is Rohan.")

    def test_favourite_things(self):
        self.assertEqual(self.ask("what is my favourite programming language"),
                         "Your favourite programming language is python.")
        self.assertEqual(self.ask("What's my favorite food?"), "Your favourite food is pizza.")
        self.assertEqual(self.ask("do you remember my favourite food"),
                         "Your favourite food is pizza.")

    def test_a_shorter_word_still_finds_the_fact(self):
        self.assertEqual(self.ask("what is my language"), "Your language is python.")

    def test_project(self):
        self.assertEqual(self.ask("what project am i currently working on"),
                         "Your project is nexus.")
        self.assertEqual(self.ask("what is my project"), "Your project is nexus.")

    def test_preferences_list_every_one(self):
        for text in ["what do i prefer", "what are my preferences",
                     "how do i like my answers", "what is my preferred style"]:
            self.assertEqual(self.ask(text), "You prefer concise explanations and short answers.", text)

    def test_the_latest_value_wins_for_single_facts(self):
        self.memory.process_memory("my name is sam")
        self.assertEqual(self.ask("what is my name"), "Your name is Sam.")

    def test_nothing_stored_means_no_answer_so_the_rest_of_nexus_runs(self):
        for text in ["what is my battery", "what is my ip address", "what is my favourite colour",
                     "what is the capital of france", "explain recursion", "what time is it",
                     "", None]:
            self.assertIsNone(self.ask(text), text)

    def test_an_empty_memory_answers_nothing(self):
        with tempfile.TemporaryDirectory() as other:
            os.chdir(other)
            empty = MemoryManager()
            self.assertIsNone(empty.answer_fact_question("what is my name"))
            self.assertIsNone(empty.facts_context())
            empty.db.close()
            os.chdir(self.dir.name)


class PromptNote(WithMemory):
    def test_the_note_lists_what_he_told_nexus(self):
        note = self.memory.facts_context()
        for part in ["name: Rohan", "programming language: python", "project: nexus",
                     "preference: concise explanations, short answers", "food: pizza"]:
            self.assertIn(part, note)

    def test_the_note_stays_short(self):
        for i in range(60):
            self.memory.process_memory(f"i like hobby number {i}")
        self.assertLessEqual(len(self.memory.facts_context()), 700)

    def test_conversation_rows_are_not_in_the_note(self):
        self.memory.save_conversation("secret question", "secret answer")
        self.assertNotIn("secret", self.memory.facts_context())


class AssistantWiring(unittest.TestCase):
    def assistant(self, facts_note="What Rohan has told you: name: Rohan."):
        from tests.test_streaming import load_assistant_class
        a = load_assistant_class().__new__(load_assistant_class())
        for name in ("conversation", "language_learner", "input_manager", "speaker",
                     "memory", "intent_fast", "llm", "intent", "observer", "knowledge"):
            setattr(a, name, MagicMock())
        a.language_learner.observe.return_value = None
        a.language_learner.get_context.return_value = None
        a.intent_fast.builtin_command.return_value = None
        a.intent_fast.is_exit_request.return_value = False
        a.intent.resolve.return_value = MagicMock(success=False, message="")
        a.conversation.get_context.return_value = [{"role": "user", "content": "hi"}]
        a.input_manager.last_input_was_voice = False
        a.memory.answer_fact_question.return_value = None
        a.memory.facts_context.return_value = facts_note
        a.response_style = MagicMock()
        a.response_style.refine.side_effect = lambda t: t
        a.get_relevant_knowledge = lambda text: ""
        a.response_displayed = False
        a.llm.generate_response.return_value = "Fine."
        return a

    def test_stored_facts_go_to_the_model_first(self):
        a = self.assistant()
        with patch.dict("os.environ", {"NEXUS_STREAM": "0"}):
            a._process_input("explain recursion")
        context = a.llm.generate_response.call_args.args[1]
        self.assertEqual(context[0], {"role": "system",
                                      "content": "What Rohan has told you: name: Rohan."})

    def test_no_facts_means_no_extra_message(self):
        a = self.assistant(facts_note=None)
        with patch.dict("os.environ", {"NEXUS_STREAM": "0"}):
            a._process_input("explain recursion")
        context = a.llm.generate_response.call_args.args[1]
        self.assertEqual(context, [{"role": "user", "content": "hi"}])

    def test_a_failure_loading_facts_does_not_break_the_reply(self):
        a = self.assistant()
        a.memory.facts_context.side_effect = RuntimeError("db locked")
        with patch.dict("os.environ", {"NEXUS_STREAM": "0"}):
            result = a._process_input("explain recursion")
        self.assertEqual(result, "Fine.")

    def test_the_real_check_memory_asks_the_fact_answers(self):
        a = self.assistant()
        a.memory.answer_fact_question.return_value = "Your name is Rohan."
        self.assertEqual(a.check_memory("what is my name"), "Your name is Rohan.")
        a.memory.answer_fact_question.return_value = None
        self.assertIsNone(a.check_memory("explain recursion"))

    def test_the_whole_profile_question_still_uses_the_profile(self):
        a = self.assistant()
        a.memory.get_memory_context.return_value = [("name", "rohan", "fact")]
        self.assertIn("Name: rohan", a.check_memory("what do you know about me"))
        a.memory.answer_fact_question.assert_not_called()

    def test_a_fact_question_is_answered_without_the_model(self):
        a = self.assistant()
        a.memory.answer_fact_question.return_value = "Your name is Rohan."
        a.check_memory = lambda text: a.memory.answer_fact_question(text)
        result = a._process_input("what is my name")
        self.assertEqual(result, "Your name is Rohan.")
        a.llm.generate_response.assert_not_called()
        a.speaker.speak.assert_called_once_with("Your name is Rohan.")


if __name__ == "__main__":
    unittest.main()
