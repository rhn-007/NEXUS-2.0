import unittest

from core.intent import greeting_response


class GreetingFastPathTests(unittest.TestCase):
    def test_standalone_greetings_get_local_replies(self):
        for greeting in (
            "hello",
            "HELLO!",
            "hi",
            "Hey Nexus",
            "good morning",
            "good afternoon",
            "good evening",
            "howdy",
        ):
            with self.subTest(greeting=greeting):
                self.assertIsNotNone(greeting_response(greeting))

    def test_time_based_greetings_get_matching_reply(self):
        self.assertTrue(greeting_response("Good morning!").startswith("Good morning"))
        self.assertTrue(greeting_response("good afternoon").startswith("Good afternoon"))
        self.assertTrue(greeting_response("good evening").startswith("Good evening"))

    def test_questions_and_requests_are_not_treated_as_greetings(self):
        for message in (
            "how are you",
            "hello, can you research robotics",
            "hey, open notepad",
            "tell me about the history of AI",
            "",
        ):
            with self.subTest(message=message):
                self.assertIsNone(greeting_response(message))


if __name__ == "__main__":
    unittest.main()
