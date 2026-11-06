import tempfile
import unittest
from pathlib import Path

from learning.personal_language import PersonalLanguageLearner


class PersonalLanguageLearnerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "language.db")
        self.learner = PersonalLanguageLearner(self.db_path)

    def tearDown(self):
        self.learner.close()
        self.temp_dir.cleanup()

    def test_learns_repeated_vocabulary_from_voice_only(self):
        self.learner.observe("NEXUS please research humanoid robotics", "voice")
        self.learner.observe("Tell me more about humanoid robotics", "voice")
        self.learner.observe("I am studying robotics", "typed")
        vocabulary = self.learner.get_vocabulary()
        self.assertIn("robotics", vocabulary)
        self.assertNotIn("studying", vocabulary)

    def test_explicit_correction_is_saved_and_used(self):
        correction = self.learner.observe(
            "When I say next us, I mean NEXUS.",
            source="typed"
        )
        self.assertEqual(correction, ("next us", "NEXUS"))
        self.assertEqual(
            self.learner.get_corrections().get("next us"),
            "NEXUS"
        )

    def test_profile_can_be_cleared(self):
        self.learner.observe("Ollama robotics", "voice")
        self.learner.add_correction("lexus", "NEXUS")
        self.learner.clear_profile()
        self.assertEqual(self.learner.get_vocabulary(), [])
        self.assertEqual(self.learner.get_corrections(), {})


if __name__ == "__main__":
    unittest.main()
