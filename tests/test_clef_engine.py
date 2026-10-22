"""Tests for Clef-Flash Decision Engine and Pluggable Model Registry."""

import unittest

from core.decision.base import DecisionQuestion
from core.decision.clef_engine import ClefDecisionEngine
from core.decision.registry import decision_registry


class TestClefDecisionEngine(unittest.TestCase):
    """Verify local-only Clef-Flash decision model scoring and registry mechanics."""

    def setUp(self):
        self.engine = ClefDecisionEngine(model_name="clef-flash")

    def test_strict_local_mode(self):
        """Ensure the engine is explicitly marked and operates strictly locally."""
        self.assertTrue(self.engine.is_local_only)
        self.assertEqual(self.engine.model_name, "clef-flash")

    def test_choice_question_prediction(self):
        question = DecisionQuestion(
            question_id="test_route",
            question_type="choice",
            instructions="Select the appropriate domain.",
            criteria={
                "spotify": "Music streaming, songs, artists, playlists",
                "terminal": "CLI shell commands, bash scripts",
            },
        )
        res = self.engine.predict(
            state="play bohemian rhapsody by queen",
            questions={"test_route": question},
        )
        self.assertIn("test_route", res)
        decision = res["test_route"]
        self.assertEqual(decision.selected_option, "spotify")
        self.assertGreater(decision.confidence, 0.5)
        self.assertTrue(decision.metadata.get("local_only"))

    def test_registry_engines(self):
        available = decision_registry.list_engines()
        self.assertIn("clef-flash", available)
        self.assertIn("clef", available)
        self.assertIn("laya", available)

        # Ensure active engine defaults to clef-flash
        self.assertEqual(decision_registry.get_active_engine_name(), "clef-flash")

        # Test switching
        self.assertTrue(decision_registry.set_active_engine("laya"))
        self.assertEqual(decision_registry.get_active_engine_name(), "laya")

        # Switch back to clef-flash
        self.assertTrue(decision_registry.set_active_engine("clef-flash"))
        self.assertEqual(decision_registry.get_active_engine_name(), "clef-flash")


if __name__ == "__main__":
    unittest.main()
