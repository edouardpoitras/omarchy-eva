"""Unit tests for Smart Application Switching with Workspace Navigation in Jarvis."""

import unittest
from unittest.mock import MagicMock, patch

from core.dispatcher import CommandDispatcher


class TestSmartAppSwitcher(unittest.TestCase):
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

    def test_open_already_running_app_switches_workspace(self):
        """When an app is already open on workspace 4, 'open spotify' should switch to ws 4 and focus."""
        # Mock Spotify open on workspace 4
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x5e6b3bcdcf40",
            "class": "Spotify",
            "initialClass": "Spotify",
            "title": "Spotify Premium",
            "workspace": {"id": 4, "name": "4"},
        }
        self.mock_hypr.focus_window_by_query.return_value = True

        res = self.dispatcher.dispatch_text("open spotify")

        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_FOCUS")
        self.assertIn("focus spotify", res["action"])
        self.assertIn("workspace 4", res["speech"])
        # Should NOT launch a new instance
        self.mock_apps.launch.assert_not_called()
        self.mock_hypr.focus_window_by_query.assert_called_with("spotify")

    def test_show_me_app_variant(self):
        """'show me spotify' or 'where is spotify' should find and focus existing window."""
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x5e6b3bcdcf40",
            "class": "Spotify",
            "initialClass": "Spotify",
            "workspace": {"id": 4, "name": "4"},
        }
        self.mock_hypr.focus_window_by_query.return_value = True

        res = self.dispatcher.dispatch_text("show me spotify")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_FOCUS")
        self.mock_apps.launch.assert_not_called()

    def test_where_is_app_query(self):
        """'where is spotify' should report workspace location without launching."""
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x5e6b3bcdcf40",
            "class": "Spotify",
            "initialClass": "Spotify",
            "workspace": {"id": 4, "name": "4"},
        }
        res = self.dispatcher.dispatch_text("where is spotify")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "HYPR_INSPECTION")
        self.assertIn("open on workspace 4", res["speech"])
        self.mock_apps.launch.assert_not_called()

    def test_open_not_running_app_launches(self):
        """When an app is not open, 'open obsidian' should launch via AppIndexer."""
        self.mock_hypr.find_open_window.return_value = None
        self.mock_hypr.focus_window_by_query.return_value = False
        self.mock_apps.find_app.return_value = {"name": "Obsidian", "id": "obsidian"}
        self.mock_apps.launch.return_value = {"success": True, "app": "Obsidian"}

        res = self.dispatcher.dispatch_text("open obsidian")

        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "APP_LAUNCH")
        self.mock_apps.launch.assert_called_once_with("obsidian")
        self.assertIn("Launching Obsidian", res["speech"])

    def test_open_app_on_specific_workspace_when_already_open(self):
        """'open spotify on workspace 4' when already open on workspace 4 should focus."""
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x5e6b3bcdcf40",
            "class": "Spotify",
            "workspace": {"id": 4, "name": "4"},
        }
        res = self.dispatcher.dispatch_text("open spotify on workspace 4")
        self.assertTrue(res["matched"])
        self.mock_hypr.focus_workspace.assert_called_with("4")
        self.mock_hypr.focus_window_address.assert_called_with("0x5e6b3bcdcf40")
        self.assertIn("already open on workspace 4", res["speech"])

    def test_open_app_on_specific_workspace_when_open_elsewhere(self):
        """'open spotify on workspace 2' when open on workspace 4 should move it to workspace 2."""
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x5e6b3bcdcf40",
            "class": "Spotify",
            "workspace": {"id": 4, "name": "4"},
        }
        res = self.dispatcher.dispatch_text("open spotify on workspace 2")
        self.assertTrue(res["matched"])
        self.mock_hypr.move_window_to_workspace.assert_called_with("2")
        self.assertIn("Moved Spotify to workspace 2", res["speech"])

    def test_open_app_on_specific_workspace_when_not_open(self):
        """'launch firefox in workspace 3' when not open should switch to ws 3 and launch."""
        self.mock_hypr.find_open_window.return_value = None
        self.mock_apps.launch.return_value = {"success": True}

        res = self.dispatcher.dispatch_text("launch firefox in workspace 3")
        self.assertTrue(res["matched"])
        self.mock_hypr.focus_workspace.assert_called_with("3")
        self.mock_apps.launch.assert_called_with("firefox")
        self.assertIn("Opening firefox on workspace 3", res["speech"])

    def test_explicit_new_instance_bypasses_focus(self):
        """'open new terminal' should launch a fresh instance even if one is running."""
        self.mock_hypr.find_open_window.return_value = {
            "address": "0x123",
            "class": "com.mitchellh.ghostty",
            "workspace": {"id": 5, "name": "5"},
        }
        self.mock_hypr.exec_app.return_value = True

        res = self.dispatcher.dispatch_text("open new terminal")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "APP_LAUNCH")
        self.mock_hypr.exec_app.assert_called_with("omarchy-default-terminal")


if __name__ == "__main__":
    unittest.main()
