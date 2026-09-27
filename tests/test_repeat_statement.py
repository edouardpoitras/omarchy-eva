"""Unit tests for Eva Repeat Last Statement and Output capability."""

import unittest
from unittest.mock import MagicMock, patch

from core.context_memory import context_memory
from core.dispatcher import CommandDispatcher


class TestRepeatStatement(unittest.TestCase):
    def setUp(self):
        context_memory.last_app = None
        context_memory.last_statement = None
        self.mock_tts = MagicMock()
        self.mock_system2 = MagicMock()
        self.mock_system2.tts = self.mock_tts
        self.dispatcher = CommandDispatcher(system2=self.mock_system2)

    def test_repeat_phrases_matching(self):
        """Test that diverse natural language repeat requests match REPEAT_STATEMENT."""
        test_phrases = [
            "repeat",
            "repeat that",
            "repeat it",
            "repeat this",
            "repeat please",
            "repeat that please",
            "say that again",
            "say again",
            "say it again",
            "can you repeat that",
            "could you say that again",
            "would you repeat that",
            "what did you say",
            "what did you just say",
            "what was that",
            "what was that again",
            "what was the last thing you said",
            "pardon",
            "pardon me",
            "come again",
            "repeat the last statement",
            "repeat the last output",
            "repeat what you said",
            "repeat yourself",
            "can you repeat what you said",
        ]
        for phrase in test_phrases:
            with self.subTest(phrase=phrase):
                res = self.dispatcher.dispatch_text(phrase, execute=False)
                self.assertTrue(res["matched"], f"Failed to match: {phrase}")
                self.assertEqual(res["intent"], "REPEAT_STATEMENT")
                self.assertEqual(res["action"], "repeat_statement")

    def test_repeat_without_prior_statement(self):
        """When no statement has been spoken yet, returns helpful empty notice."""
        res = self.dispatcher.dispatch_text("repeat that", execute=True)
        self.assertTrue(res["matched"])
        self.assertEqual(res["speech"], "I haven't said anything yet.")
        self.mock_tts.speak.assert_called_with("I haven't said anything yet.", block=False)

    def test_repeat_prior_reflex_speech(self):
        """Verify that speech from a prior command is accurately repeated."""
        # 1. Execute a command that generates speech
        self.dispatcher.hypr.get_active_workspace = MagicMock(return_value="3")
        res1 = self.dispatcher.dispatch_text("what workspace am i on", execute=True)
        self.assertTrue(res1["matched"])
        first_speech = res1.get("speech")
        self.assertIsNotNone(first_speech)
        self.assertIn("workspace", first_speech.lower())

        # 2. Ask to repeat
        self.mock_tts.reset_mock()
        res2 = self.dispatcher.dispatch_text("what did you say", execute=True)
        self.assertTrue(res2["matched"])
        self.assertEqual(res2["speech"], first_speech)
        self.mock_tts.speak.assert_called_with(first_speech, block=False)

    def test_repeat_multiple_times_preserves_original(self):
        """Repeating multiple times should preserve the original statement and not clobber it."""
        context_memory.record_statement("The CPU temperature is 42 degrees Celsius.")

        res1 = self.dispatcher.dispatch_text("repeat that", execute=True)
        self.assertEqual(res1["speech"], "The CPU temperature is 42 degrees Celsius.")

        # Second repetition must still repeat original statement
        res2 = self.dispatcher.dispatch_text("say that again", execute=True)
        self.assertEqual(res2["speech"], "The CPU temperature is 42 degrees Celsius.")

        # Third repetition with another phrase
        res3 = self.dispatcher.dispatch_text("pardon", execute=True)
        self.assertEqual(res3["speech"], "The CPU temperature is 42 degrees Celsius.")

    def test_anaphora_guard_for_repeat(self):
        """Ensure pronoun resolution does not corrupt repeat commands when app is in memory."""
        context_memory.record(intent="HYPR_FOCUS", action="focus spotify", app="spotify")
        self.assertEqual(context_memory.last_app, "spotify")

        # 'repeat that' should NOT be rewritten to 'repeat spotify'
        res = self.dispatcher.dispatch_text("repeat that", execute=False)
        self.assertEqual(res["intent"], "REPEAT_STATEMENT")
        self.assertEqual(res["action"], "repeat_statement")


if __name__ == "__main__":
    unittest.main()
