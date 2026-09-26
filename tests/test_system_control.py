"""Unit tests for System Control and Telemetry module."""

import unittest
from unittest.mock import patch, MagicMock

from core.system_control import SystemControl


class TestSystemControl(unittest.TestCase):
    """Test suite for system power, telemetry, and app closing."""

    def setUp(self):
        self.sys = SystemControl()

    @patch("subprocess.run")
    def test_get_top_processes(self, mock_run):
        """Test parsing ps output for top CPU and Memory processes."""
        mock_output = """COMMAND         %CPU %MEM
antigravity     45.2  3.1
ghostty         12.0  1.5
firefox          8.5  5.0
ps               0.1  0.0
"""
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)

        res = self.sys.get_top_processes(by="cpu", count=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["processes"][0]["name"], "antigravity")
        self.assertEqual(res["processes"][0]["cpu"], 45.2)
        self.assertIn("antigravity at 45.2 percent", res["speech"])

    @patch("subprocess.run")
    def test_close_app_hyprland(self, mock_run):
        """Test closing app by matching Hyprland client title/class."""
        mock_clients = """[
            {"address": "0x123456", "class": "ghostty", "title": "eddie@omarchy:~", "initialClass": "com.mitchellh.ghostty"},
            {"address": "0x789abc", "class": "firefox", "title": "Mozilla Firefox", "initialClass": "firefox"}
        ]"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=mock_clients),  # hyprctl clients -j
            MagicMock(returncode=0, stdout=""),            # hyprctl dispatch closewindow
        ]

        res = self.sys.close_app("ghostty")
        self.assertTrue(res["success"])
        self.assertEqual(res["closed_count"], 1)
        self.assertIn("ghostty", res["message"])

    @patch("subprocess.Popen")
    def test_power_action(self, mock_popen):
        """Test power actions dispatch systemctl and loginctl commands."""
        res_shutdown = self.sys.power_action("shutdown")
        self.assertTrue(res_shutdown["success"])
        self.assertEqual(res_shutdown["action"], "shutdown")

        res_reboot = self.sys.power_action("reboot")
        self.assertTrue(res_reboot["success"])
        self.assertEqual(res_reboot["action"], "reboot")

        res_lock = self.sys.power_action("lock")
        self.assertTrue(res_lock["success"])
        self.assertEqual(res_lock["action"], "lock")

        res_invalid = self.sys.power_action("explode")
        self.assertFalse(res_invalid["success"])

    def test_disk_space(self):
        """Test reading filesystem disk space."""
        res = self.sys.get_disk_space()
        self.assertTrue(res["success"])
        self.assertGreater(res["total_gb"], 0)
        self.assertIn("gigabytes free out of", res["speech"])

    def test_ram_status(self):
        """Test reading /proc/meminfo memory status."""
        res = self.sys.get_ram_status()
        self.assertTrue(res["success"])
        self.assertGreater(res["total_gb"], 0)
        self.assertIn("gigabytes of RAM available", res["speech"])

    def test_time_date(self):
        """Test formatted time and date string."""
        res = self.sys.get_time_date()
        self.assertTrue(res["success"])
        self.assertIn("The time is", res["speech"])

    def test_local_ip(self):
        """Test reading local network IP address."""
        res = self.sys.get_local_ip()
        self.assertTrue(res["success"])
        self.assertTrue(len(res["ip"].split(".")) == 4)

    @patch("subprocess.run")
    def test_read_clipboard(self, mock_run):
        """Test reading Wayland clipboard content."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Eva voice automation")
        res = self.sys.read_clipboard()
        self.assertTrue(res["success"])
        self.assertEqual(res["text"], "Eva voice automation")
        self.assertIn("Eva voice automation", res["speech"])


if __name__ == "__main__":
    unittest.main()
