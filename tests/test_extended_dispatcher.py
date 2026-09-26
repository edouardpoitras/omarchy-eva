"""Unit tests for extended reflex actions in CommandDispatcher."""

import unittest
from unittest.mock import MagicMock

from core.dispatcher import CommandDispatcher


class TestExtendedDispatcher(unittest.TestCase):
    """Test suite for new quick actions: visual click, app launch, close, top processes, and telemetry."""

    def setUp(self):
        self.mock_hypr = MagicMock()
        self.mock_media = MagicMock()
        self.mock_laya = MagicMock()
        self.mock_laya.predict.return_value = {"available": False, "intent": "UNKNOWN", "confident": False}

        self.mock_apps = MagicMock()
        self.mock_system = MagicMock()
        self.mock_visual = MagicMock()

        self.dispatcher = CommandDispatcher(
            hypr=self.mock_hypr,
            media=self.mock_media,
            laya=self.mock_laya,
            apps=self.mock_apps,
            system=self.mock_system,
            visual=self.mock_visual,
        )

    def test_dispatch_visual_click(self):
        """Test dispatching 'click on the red button'."""
        self.mock_visual.locate_and_click.return_value = {
            "success": True,
            "x": 640,
            "y": 480,
            "speech": "Clicked on red button.",
        }

        res = self.dispatcher.dispatch_text("click on the red button")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "VISUAL_CLICK")
        self.mock_visual.locate_and_click.assert_called_once_with(
            "red button", button="left", double=False
        )

    def test_dispatch_double_click(self):
        """Test dispatching 'double click on file'."""
        self.mock_visual.locate_and_click.return_value = {
            "success": True,
            "x": 100,
            "y": 200,
            "speech": "Double clicked on file.",
        }

        res = self.dispatcher.dispatch_text("double click on file")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "VISUAL_CLICK")
        self.mock_visual.locate_and_click.assert_called_once_with(
            "file", button="left", double=True
        )

    def test_dispatch_top_processes_cpu(self):
        """Test dispatching 'top 3 processes by cpu'."""
        self.mock_system.get_top_processes.return_value = {
            "success": True,
            "by": "CPU",
            "count": 3,
            "processes": [{"name": "antigravity", "cpu": 50.0}],
            "speech": "Top process by CPU is antigravity at 50 percent.",
        }

        res = self.dispatcher.dispatch_text("top 3 processes by cpu")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "SYSTEM_TELEMETRY")
        self.mock_system.get_top_processes.assert_called_once_with(by="cpu", count=3)

    def test_dispatch_app_close(self):
        """Test dispatching 'close ghostty'."""
        self.mock_system.close_app.return_value = {
            "success": True,
            "message": "Closed ghostty.",
        }

        res = self.dispatcher.dispatch_text("close ghostty")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "APP_CLOSE")
        self.mock_system.close_app.assert_called_once_with("ghostty")

    def test_dispatch_app_launch(self):
        """Test dispatching 'open obsidian' via AppIndexer."""
        self.mock_apps.find_app.return_value = {"name": "Obsidian", "id": "obsidian"}
        self.mock_apps.launch.return_value = {"success": True, "app": "Obsidian"}

        res = self.dispatcher.dispatch_text("open obsidian")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "APP_LAUNCH")
        self.mock_apps.launch.assert_called_once_with("obsidian")

    def test_dispatch_disk_space(self):
        """Test dispatching 'how much disk space'."""
        self.mock_system.get_disk_space.return_value = {
            "success": True,
            "free_gb": 1600,
            "speech": "You have 1600 GB free.",
        }

        res = self.dispatcher.dispatch_text("how much disk space")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "SYSTEM_TELEMETRY")
        self.mock_system.get_disk_space.assert_called_once()

    def test_dispatch_power_shutdown(self):
        """Test dispatching 'shut down'."""
        self.mock_system.power_action.return_value = {
            "success": True,
            "speech": "Initiating system shutdown.",
        }

        res = self.dispatcher.dispatch_text("shut down")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "SYSTEM_POWER")
        self.mock_system.power_action.assert_called_once_with("shutdown")


if __name__ == "__main__":
    unittest.main()
