"""Unit tests for Compound Multi-Step Command Execution in Jarvis."""

import unittest
from unittest.mock import MagicMock

from core.dispatcher import CommandDispatcher, split_compound_commands


class TestCompoundCommands(unittest.TestCase):
    def setUp(self):
        self.mock_hypr = MagicMock()
        self.mock_apps = MagicMock()
        self.mock_media = MagicMock()
        self.mock_system = MagicMock()
        self.mock_system2 = MagicMock()

        self.dispatcher = CommandDispatcher(
            hypr=self.mock_hypr,
            apps=self.mock_apps,
            media=self.mock_media,
            system=self.mock_system,
            system2=self.mock_system2,
        )

    def test_split_compound_commands(self):
        """Test parsing and decomposition of compound instructions."""
        self.assertEqual(
            split_compound_commands("switch to workspace 2 and open ghostty"),
            ["switch to workspace 2", "open ghostty"],
        )
        self.assertEqual(
            split_compound_commands("open spotify and pause music"),
            ["open spotify", "pause music"],
        )
        self.assertEqual(
            split_compound_commands("mute audio and lock screen"),
            ["mute audio", "lock screen"],
        )
        self.assertEqual(
            split_compound_commands("turn up volume then next track"),
            ["turn up volume", "next track"],
        )
        self.assertEqual(
            split_compound_commands("pause music and then switch to workspace 1"),
            ["pause music", "switch to workspace 1"],
        )
        # Verify protected phrases are not split
        self.assertEqual(
            split_compound_commands("drag and drop file"),
            ["drag and drop file"],
        )
        self.assertEqual(
            split_compound_commands("what time and date is it"),
            ["what time and date is it"],
        )

    def test_execute_compound_switch_workspace_and_open_app(self):
        """'switch to workspace 2 and open ghostty' executes both in sequence."""
        self.mock_hypr.focus_workspace.return_value = True
        self.mock_hypr.find_open_window.return_value = None
        self.mock_apps.find_app.return_value = {"name": "Ghostty", "id": "ghostty"}
        self.mock_apps.launch.return_value = {"success": True}

        res = self.dispatcher.dispatch_text("switch to workspace 2 and open ghostty")

        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "COMPOUND_REFLEX")
        self.assertTrue(res["success"])
        self.assertIn("workspace 2", res["action"])
        self.assertIn("launch Ghostty", res["action"])
        self.mock_hypr.focus_workspace.assert_called_with("2")
        self.mock_apps.launch.assert_called_with("ghostty")
        # Ensure System 2 LLM was never called
        self.mock_system2.query.assert_not_called()

    def test_execute_compound_open_spotify_and_pause_music(self):
        """'open spotify and pause music' switches to Spotify and pauses playback."""
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x5e6b3bcdcf40",
            "class": "Spotify",
            "workspace": {"id": 4, "name": "4"},
        }
        self.mock_hypr.focus_window_by_query.return_value = True
        self.mock_media.pause.return_value = True

        res = self.dispatcher.dispatch_text("open spotify and pause music")

        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "COMPOUND_REFLEX")
        self.assertTrue(res["success"])
        self.mock_hypr.focus_window_by_query.assert_called_with("spotify")
        self.mock_media.pause.assert_called_once()
        self.mock_system2.query.assert_not_called()

    def test_execute_compound_mute_and_lock(self):
        """'mute audio and lock screen' executes audio mute and loginctl lock."""
        self.mock_media.toggle_mute_output.return_value = True
        self.dispatcher._launch_cmd = MagicMock(return_value=True)

        res = self.dispatcher.dispatch_text("mute audio and lock screen")

        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "COMPOUND_REFLEX")
        self.mock_media.toggle_mute_output.assert_called_once()
        self.dispatcher._launch_cmd.assert_called_with(["loginctl", "lock-session"])

    def test_compound_with_generative_falls_back_to_system2(self):
        """If one part requires generative System 2, entire command falls back cleanly."""
        self.mock_system2.query.return_value = {
            "status": "ok",
            "response": "Here is the explanation, sir.",
            "requires_clarification": False,
        }

        res = self.dispatcher.dispatch_text("switch to workspace 2 and explain quantum computing")
        # Should fall back to System 2 without partial execution
        self.assertEqual(res["intent"], "ESCALATE_GENERATIVE")
        self.mock_system2.query.assert_called_once()


if __name__ == "__main__":
    unittest.main()
