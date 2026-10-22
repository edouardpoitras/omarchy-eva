"""Tests for Hierarchical System 1 Router and Domain Models."""

import unittest

from core.decision.clef_engine import ClefDecisionEngine
from core.decision.router import HierarchicalRouter


class TestHierarchicalRouter(unittest.TestCase):
    """Verify hierarchical routing from high-level router to application leaf models."""

    def setUp(self):
        self.engine = ClefDecisionEngine(model_name="clef-flash")
        self.router = HierarchicalRouter(engine=self.engine)

    def test_route_spotify_song(self):
        res = self.router.route_and_execute("play bohemian rhapsody by queen", execute=False)
        self.assertEqual(res["domain"], "spotify")
        self.assertEqual(res["action"], "play_track_artist")
        self.assertEqual(res["tokens"]["track"].lower(), "bohemian rhapsody")
        self.assertEqual(res["tokens"]["artist"].lower(), "queen")
        self.assertFalse(res["escalate"])

    def test_route_system_media_pause(self):
        res = self.router.route_and_execute("pause currently playing media", execute=False)
        self.assertEqual(res["domain"], "media_playback")
        self.assertEqual(res["action"], "pause")
        self.assertFalse(res["escalate"])

    def test_route_window_manager(self):
        res = self.router.route_and_execute("switch to workspace 3", execute=False)
        self.assertEqual(res["domain"], "window_manager")
        self.assertEqual(res["action"], "switch_workspace")
        self.assertEqual(res["tokens"]["workspace"], "3")

    def test_route_terminal(self):
        res = self.router.route_and_execute("run ls -la in terminal", execute=False)
        self.assertEqual(res["domain"], "terminal")
        self.assertEqual(res["action"], "run_command")
        self.assertEqual(res["tokens"]["command"], "ls -la")

    def test_route_browser(self):
        res = self.router.route_and_execute("search google for rust programming", execute=False)
        self.assertEqual(res["domain"], "web_browser")
        self.assertEqual(res["action"], "search_web")
        self.assertEqual(res["tokens"]["query"], "rust programming")

    def test_route_screen_gui(self):
        res = self.router.route_and_execute("click on the submit button", execute=False)
        self.assertEqual(res["domain"], "screen_gui")
        self.assertEqual(res["action"], "click_element")
        self.assertEqual(res["tokens"]["target"], "submit button")

    def test_route_system_control(self):
        res = self.router.route_and_execute("what is my battery level", execute=False)
        self.assertEqual(res["domain"], "system_control")
        self.assertEqual(res["action"], "battery")

    def test_route_generative_fallback(self):
        res = self.router.route_and_execute("explain the theory of relativity in detail", execute=False)
        self.assertEqual(res["domain"], "generative_fallback")
        self.assertTrue(res["escalate"])


if __name__ == "__main__":
    unittest.main()
