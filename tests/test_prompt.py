import unittest

from ai.prompts import SYSTEM_PROMPT


class PromptTests(unittest.TestCase):
    def test_personality_rules_are_still_there(self):
        for text in [
            "You are NEXUS, Rohan's personal AI assistant.",
            "Do not use customer-service language.",
            "Never claim to have done something that has not actually happened.",
            "Do not use emojis unless Rohan explicitly asks for them.",
            "Do not constantly use his name.",
            "The goal is for NEXUS to feel natural, capable, and dependable.",
        ]:
            self.assertIn(text, SYSTEM_PROMPT)

    def test_it_knows_what_nexus_can_do_without_overclaiming(self):
        self.assertIn("CAPABILITIES:", SYSTEM_PROMPT)
        self.assertIn("open apps, folders and websites", SYSTEM_PROMPT)
        self.assertIn("the action did not run", SYSTEM_PROMPT)
        self.assertIn("do not claim you did them", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
