"""Unit tests for the Jarvis Core reflex command dispatcher."""

import unittest
from unittest.mock import MagicMock

from core.dispatcher import CommandDispatcher, normalize_numbers


class TestCommandDispatcher(unittest.TestCase):
    """Test suite for intent classification and dispatch parameter extraction."""

    def setUp(self):
        self.mock_hypr = MagicMock()
        self.mock_hypr.focus_workspace.return_value = True
        self.mock_hypr.move_window_to_workspace.return_value = True
        self.mock_hypr.close_window.return_value = True
        self.mock_hypr.toggle_fullscreen.return_value = True
        self.mock_hypr.toggle_floating.return_value = True
        self.mock_hypr.exec_app.return_value = True
        self.mock_hypr.focus_window_by_query.return_value = True

        self.mock_media = MagicMock()
        self.mock_media.pause.return_value = True
        self.mock_media.play.return_value = True
        self.mock_media.play_pause.return_value = True
        self.mock_media.next_track.return_value = True
        self.mock_media.previous_track.return_value = True
        self.mock_media.volume_up.return_value = True
        self.mock_media.volume_down.return_value = True
        self.mock_media.set_volume.return_value = True
        self.mock_media.set_mic_mute.return_value = True
        self.mock_media.toggle_mute_output.return_value = True

        self.mock_laya = MagicMock()
        self.mock_laya.predict.return_value = {
            "available": True,
            "intent": "UNKNOWN",
            "confidence": 0.0,
            "confident": False,
            "distribution": {},
            "latency_ms": 0.5,
        }

        self.dispatcher = CommandDispatcher(
            hypr=self.mock_hypr, media=self.mock_media, laya=self.mock_laya
        )

    def test_normalize_numbers(self):
        """Test spoken number word normalization."""
        self.assertEqual(
            normalize_numbers("switch to workspace three"),
            "switch to workspace 3",
        )
        self.assertEqual(
            normalize_numbers("go to workspace ten"),
            "go to workspace 10",
        )
        self.assertEqual(
            normalize_numbers("move to desktop five"),
            "move to desktop 5",
        )

    def test_workspace_dispatch(self):
        """Test workspace switching and navigation commands."""
        # Absolute workspace
        res = self.dispatcher.dispatch_text("switch to workspace three")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_WORKSPACE")
        self.assertEqual(res["action"], "workspace 3")
        self.mock_hypr.focus_workspace.assert_called_with("3")

        # Relative next workspace
        res = self.dispatcher.dispatch_text("next workspace")
        self.assertTrue(res["matched"])
        self.assertEqual(res["action"], "workspace +1")
        self.mock_hypr.focus_workspace.assert_called_with("e+1")

        # Relative previous workspace
        res = self.dispatcher.dispatch_text("previous workspace")
        self.assertTrue(res["matched"])
        self.assertEqual(res["action"], "workspace -1")
        self.mock_hypr.focus_workspace.assert_called_with("e-1")

        # Move active window to workspace
        res = self.dispatcher.dispatch_text("move window to workspace 4")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_WINDOW_MOVE")
        self.assertEqual(res["action"], "movetoworkspace 4")
        self.mock_hypr.move_window_to_workspace.assert_called_with("4")

    def test_window_manipulation(self):
        """Test window layout, close, and focus commands."""
        # Close active
        res = self.dispatcher.dispatch_text("close this window")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_WINDOW")
        self.mock_hypr.close_window.assert_called_once()

        # Fullscreen
        res = self.dispatcher.dispatch_text("make fullscreen")
        self.assertTrue(res["matched"])
        self.mock_hypr.toggle_fullscreen.assert_called_once()

        # Toggle floating
        res = self.dispatcher.dispatch_text("toggle floating")
        self.assertTrue(res["matched"])
        self.mock_hypr.toggle_floating.assert_called_once()

        # Focus specific app
        res = self.dispatcher.dispatch_text("focus neovim")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_FOCUS")
        self.mock_hypr.focus_window_by_query.assert_called_with("neovim")

    def test_media_control(self):
        """Test MPRIS playback and volume commands."""
        # Pause
        res = self.dispatcher.dispatch_text("pause the music")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "MEDIA_CONTROL")
        self.mock_media.pause.assert_called_once()

        # Play / resume
        res = self.dispatcher.dispatch_text("resume playback")
        self.assertTrue(res["matched"])
        self.mock_media.play.assert_called_once()

        # Next / skip
        res = self.dispatcher.dispatch_text("skip this song")
        self.assertTrue(res["matched"])
        self.mock_media.next_track.assert_called_once()

        # Volume up/down
        res = self.dispatcher.dispatch_text("turn it up")
        self.assertTrue(res["matched"])
        self.mock_media.volume_up.assert_called_with(5)

        res = self.dispatcher.dispatch_text("volume down")
        self.assertTrue(res["matched"])
        self.mock_media.volume_down.assert_called_with(5)

        res = self.dispatcher.dispatch_text("set volume to 80 percent")
        self.assertTrue(res["matched"])
        self.mock_media.set_volume.assert_called_with(80)

        # Mute and unmute microphone
        res = self.dispatcher.dispatch_text("unmute mic")
        self.assertTrue(res["matched"])
        self.mock_media.set_mic_mute.assert_called_with(False)

        res = self.dispatcher.dispatch_text("mute mic!")
        self.assertTrue(res["matched"])
        self.mock_media.set_mic_mute.assert_called_with(True)

    def test_app_launchers(self):
        """Test application launching commands."""
        # Terminal
        res = self.dispatcher.dispatch_text("open terminal")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "APP_LAUNCH")
        self.mock_hypr.exec_app.assert_called_with("omarchy-default-terminal")

        # Browser
        res = self.dispatcher.dispatch_text("launch browser")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "APP_LAUNCH")
        self.mock_hypr.exec_app.assert_called_with("omarchy-default-browser")

    def test_unmatched_fallback(self):
        """Test that complex or open-ended instructions properly fall back."""
        res = self.dispatcher.dispatch_text("explain quantum computing to me")
        self.assertFalse(res["matched"])
        self.assertEqual(res["intent"], "UNKNOWN")
        self.assertIsNone(res["action"])

    def test_laya_escalation(self):
        """Test that high-confidence ESCALATE_GENERATIVE from Laya triggers System 2 escalation."""
        self.mock_laya.predict.return_value = {
            "available": True,
            "intent": "ESCALATE_GENERATIVE",
            "confidence": 0.995,
            "confident": True,
            "distribution": {"ESCALATE_GENERATIVE": 0.995},
            "latency_ms": 15.0,
        }
        res = self.dispatcher.dispatch_text("why is the bluetooth daemon failing?")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "ESCALATE_GENERATIVE")
        self.assertEqual(res["action"], "escalate_to_system2")


if __name__ == "__main__":
    unittest.main()
