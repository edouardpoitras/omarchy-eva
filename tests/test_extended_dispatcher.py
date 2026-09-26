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

    def test_dispatch_directional_navigation(self):
        """Test directional window focus, swapping, and scratchpad."""
        self.mock_hypr.focus_direction.return_value = True
        self.mock_hypr.swap_window_direction.return_value = True
        self.mock_hypr.toggle_scratchpad.return_value = True
        self.mock_hypr.move_to_scratchpad.return_value = True

        res = self.dispatcher.dispatch_text("focus left")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_FOCUS")
        self.mock_hypr.focus_direction.assert_called_with("left")

        res = self.dispatcher.dispatch_text("swap window right")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_WINDOW")
        self.mock_hypr.swap_window_direction.assert_called_with("right")

        res = self.dispatcher.dispatch_text("toggle scratchpad")
        self.assertTrue(res["matched"])
        self.mock_hypr.toggle_scratchpad.assert_called_once()

        res = self.dispatcher.dispatch_text("send to scratchpad")
        self.assertTrue(res["matched"])
        self.mock_hypr.move_to_scratchpad.assert_called_once()

    def test_dispatch_window_and_workspace_queries(self):
        """Test active window and workspace inspection queries."""
        self.mock_hypr.get_active_window.return_value = {
            "class": "Spotify",
            "title": "Starship Flight 5",
            "workspace": {"name": "4"},
        }
        self.mock_hypr.get_json.return_value = {"id": 4, "name": "4"}

        res = self.dispatcher.dispatch_text("what window is this")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_INSPECTION")
        self.assertIn("Spotify", res["speech"])

        res = self.dispatcher.dispatch_text("what workspace am I on")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_INSPECTION")
        self.assertIn("workspace 4", res["speech"])

    def test_dispatch_media_song_query(self):
        """Test 'what song is this' / 'current track' query."""
        self.mock_system.get_current_track.return_value = {
            "success": True,
            "playing": True,
            "speech": "Currently playing 'Starship' by SpaceX on Spotify.",
        }

        res = self.dispatcher.dispatch_text("what song is this")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "MEDIA_QUERY")
        self.assertIn("Starship", res["speech"])
        self.mock_system.get_current_track.assert_called_once()

    def test_dispatch_device_controls(self):
        """Test WiFi, Bluetooth, DND, stay-awake, and top bar toggles."""
        self.mock_system.toggle_wifi.return_value = {"success": True, "speech": "Wi-Fi is now enabled."}
        self.mock_system.toggle_bluetooth.return_value = {"success": True, "speech": "Bluetooth is now enabled."}
        self.mock_system.toggle_dnd.return_value = {"success": True, "speech": "Do not disturb mode toggled."}
        self.mock_system.toggle_idle.return_value = {"success": True, "speech": "Stay-awake mode activated."}
        self.mock_system.toggle_bar.return_value = {"success": True, "speech": "Top bar toggled."}

        res = self.dispatcher.dispatch_text("turn on wifi")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DEVICE_CONTROL")
        self.mock_system.toggle_wifi.assert_called_with("on")

        res = self.dispatcher.dispatch_text("turn on bluetooth")
        self.assertTrue(res["matched"])
        self.mock_system.toggle_bluetooth.assert_called_with("on")

        res = self.dispatcher.dispatch_text("do not disturb")
        self.assertTrue(res["matched"])
        self.mock_system.toggle_dnd.assert_called_once()

        res = self.dispatcher.dispatch_text("stay awake")
        self.assertTrue(res["matched"])
        self.mock_system.toggle_idle.assert_called_with("stay-awake")

        res = self.dispatcher.dispatch_text("toggle bar")
        self.assertTrue(res["matched"])
        self.mock_system.toggle_bar.assert_called_once()

    def test_dispatch_uptime_and_temperature(self):
        """Test system uptime and cpu temperature telemetry."""
        self.mock_system.get_uptime.return_value = {"success": True, "speech": "The system has been running for 5 hours."}
        self.mock_system.get_cpu_temperature.return_value = {"success": True, "speech": "Current average temperature is 45 degrees Celsius."}

        res = self.dispatcher.dispatch_text("system uptime")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "SYSTEM_TELEMETRY")
        self.mock_system.get_uptime.assert_called_once()

        res = self.dispatcher.dispatch_text("cpu temperature")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "SYSTEM_TELEMETRY")
        self.mock_system.get_cpu_temperature.assert_called_once()

    def test_dispatch_directory_shortcuts(self):
        """Test opening standard user directories."""
        self.mock_system.open_directory.return_value = {"success": True, "speech": "Opening downloads directory."}

        res = self.dispatcher.dispatch_text("open downloads")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DIR_SHORTCUT")
        self.mock_system.open_directory.assert_called_with("downloads")


if __name__ == "__main__":
    unittest.main()

