"""Tests for Multi-Turn Command History and Context Tracking."""

import unittest

from core.context_memory import ContextMemory
from core.decision.clef_engine import ClefDecisionEngine
from core.decision.router import HierarchicalRouter


class TestContextHistory(unittest.TestCase):
    """Verify conversational context memory, turn history, and follow-up routing."""

    def setUp(self):
        self.memory = ContextMemory(ttl_seconds=60.0)
        self.engine = ClefDecisionEngine(model_name="clef-flash")
        self.router = HierarchicalRouter(engine=self.engine)

    def test_record_turn_history(self):
        self.memory.record_turn(
            input_text="open spotify",
            domain="spotify",
            action="open_spotify",
            tokens={"app": "spotify"},
            success=True,
        )
        self.assertEqual(len(self.memory.history), 1)
        self.assertEqual(self.memory.history[0]["domain"], "spotify")

        snapshot = self.memory.get_context_snapshot()
        self.assertEqual(len(snapshot["command_history"]), 1)

    def test_follow_up_with_history(self):
        # 1. Turn 1: open spotify
        self.memory.record_turn(
            input_text="open spotify",
            domain="spotify",
            action="open_spotify",
            tokens={"app": "spotify"},
            success=True,
        )

        # 2. Turn 2: play bohemian rhapsody
        snapshot = self.memory.get_context_snapshot()
        res = self.router.route_and_execute("play bohemian rhapsody by queen", context=snapshot, execute=False)
        self.assertEqual(res["domain"], "spotify")
        self.assertEqual(res["action"], "play_track_artist")

        self.memory.record_turn(
            input_text="play bohemian rhapsody by queen",
            domain="spotify",
            action="play_track_artist",
            tokens=res["tokens"],
            success=True,
        )

        # 3. Turn 3: "now pause it"
        snapshot2 = self.memory.get_context_snapshot()
        res2 = self.router.route_and_execute("pause playback", context=snapshot2, execute=False)
        self.assertEqual(res2["domain"], "media_playback")
        self.assertEqual(res2["action"], "pause")


if __name__ == "__main__":
    unittest.main()
