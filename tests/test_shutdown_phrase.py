import subprocess
import unittest

from core.power_command import ShutdownPhraseHandler


class ShutdownPhraseHandlerTests(unittest.TestCase):

    def setUp(self):
        self.calls = []
        self.now = 100.0

        def runner(command, **kwargs):
            self.calls.append((command, kwargs))

        self.handler = ShutdownPhraseHandler(
            runner=runner,
            clock=lambda: self.now,
            platform_name="win32"
        )

    def test_exact_trigger_requests_confirmation_only(self):
        response = self.handler.handle("Green apple!")
        self.assertIn("confirm shutdown", response)
        self.assertEqual(self.calls, [])

    def test_phrase_inside_normal_sentence_is_ignored(self):
        self.assertIsNone(self.handler.handle("I ate a green apple today"))
        self.assertEqual(self.calls, [])

    def test_question_about_phrase_is_ignored(self):
        self.assertIsNone(self.handler.handle("What is a green apple?"))
        self.assertEqual(self.calls, [])

    def test_confirmation_without_pending_request_is_ignored(self):
        self.assertIsNone(self.handler.handle("confirm shutdown"))
        self.assertEqual(self.calls, [])

    def test_confirmation_schedules_shutdown_after_trigger(self):
        self.handler.handle("green apple")
        response = self.handler.handle("confirm shutdown")
        self.assertIn("30 seconds", response)
        self.assertEqual(self.calls[0][0], ["shutdown", "/s", "/t", "30"])

    def test_cancel_before_confirmation(self):
        self.handler.handle("green apple")
        response = self.handler.handle("cancel")
        self.assertIn("cancelled", response.lower())
        self.assertEqual(self.calls, [])

    def test_cancel_after_scheduling(self):
        self.handler.handle("green apple")
        self.handler.handle("confirm shutdown")
        response = self.handler.handle("cancel shutdown")
        self.assertIn("cancelled", response.lower())
        self.assertEqual(self.calls[-1][0], ["shutdown", "/a"])

    def test_confirmation_expires(self):
        self.handler.handle("green apple")
        self.now += 16
        response = self.handler.handle("confirm shutdown")
        self.assertIn("expired", response.lower())
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

