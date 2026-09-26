"""Unit tests for the Proactive Jarvis Awareness Engine."""

import unittest
from unittest.mock import patch, MagicMock

from core.awareness_engine import AwarenessEngine


class TestAwarenessEngine(unittest.TestCase):
    """Test suite for background watchdogs, debounce, and proactive alerts."""

    def setUp(self):
        self.mock_alert = MagicMock()
        self.mock_agent = MagicMock()
        self.engine = AwarenessEngine(
            alert_callback=self.mock_alert,
            query_agent_callback=self.mock_agent,
            cpu_threshold=80.0,
            ram_min_gb=4.0,
            disk_min_gb=10.0,
            battery_min_pct=20,
            enabled=True,
        )

    def test_cooldown_debounce(self):
        """Test that alert cooldown prevents spamming repetitive warnings."""
        self.assertTrue(self.engine._can_alert("cpu"))

        # Trigger first alert
        self.engine.trigger_alert("cpu", "High CPU", "CPU load is 95%")
        self.mock_alert.assert_called_once()

        # Immediate follow-up should be blocked by cooldown
        self.assertFalse(self.engine._can_alert("cpu"))
        self.engine.trigger_alert("cpu", "High CPU", "CPU load is still 95%")
        self.assertEqual(self.mock_alert.call_count, 1)

        # Different category should still be allowed
        self.assertTrue(self.engine._can_alert("disk"))

    def test_network_transition_alerts(self):
        """Test alerting on network disconnect and reconnect transitions."""
        # Initial offline state
        self.engine._is_online = True

        # Simulate network lost
        with patch.object(self.engine, "check_network_connectivity", return_value=False):
            self.engine._evaluate_network()
            self.mock_alert.assert_called_once()
            args, kwargs = self.mock_alert.call_args
            self.assertEqual(kwargs.get("title"), "Network Disconnected")
            self.assertIn("lost", kwargs.get("speech", ""))

        self.mock_alert.reset_mock()

        # Simulate network restored
        with patch.object(self.engine, "check_network_connectivity", return_value=True):
            self.engine._evaluate_network()
            self.mock_alert.assert_called_once()
            args, kwargs = self.mock_alert.call_args
            self.assertEqual(kwargs.get("title"), "Network Restored")
            self.assertIn("restored", kwargs.get("speech", ""))

    def test_resource_evaluations(self):
        """Test CPU, RAM, and Disk threshold triggers."""
        # CPU spike
        with patch.object(self.engine, "check_cpu_usage", return_value=92.5):
            with patch.object(self.engine, "check_ram_available_gb", return_value=16.0):
                with patch.object(self.engine, "check_disk_free_gb", return_value=100.0):
                    with patch.object(self.engine, "check_battery", return_value=None):
                        self.engine._evaluate_resources()
                        self.mock_alert.assert_called_once()
                        self.assertEqual(self.mock_alert.call_args[1].get("title"), "High CPU Load")

        self.mock_alert.reset_mock()

        # Low RAM trigger
        with patch.object(self.engine, "check_cpu_usage", return_value=10.0):
            with patch.object(self.engine, "check_ram_available_gb", return_value=2.1):
                with patch.object(self.engine, "check_disk_free_gb", return_value=100.0):
                    with patch.object(self.engine, "check_battery", return_value=None):
                        self.engine._evaluate_resources()
                        self.mock_alert.assert_called_once()
                        self.assertEqual(self.mock_alert.call_args[1].get("title"), "Low Available Memory")

    @patch("subprocess.run")
    def test_journal_anomaly_with_agent(self, mock_run):
        """Test parsing fatal journal entries and consulting System 2 agent."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="kernel: Out of memory: Killed process 9999 (heavy_task)\n",
        )
        self.mock_agent.return_value = {
            "response": "Sir, the system terminated heavy_task due to memory exhaustion."
        }

        self.engine._evaluate_journal()
        self.mock_alert.assert_called_once()
        kwargs = self.mock_alert.call_args[1]
        self.assertEqual(kwargs.get("title"), "System Anomaly Logged")
        self.assertEqual(
            kwargs.get("speech"),
            "Sir, the system terminated heavy_task due to memory exhaustion.",
        )

    def test_get_status(self):
        """Test diagnostic status output dictionary."""
        status = self.engine.get_status()
        self.assertTrue(status["enabled"])
        self.assertIn("cooldowns", status)
        self.assertIn("stats", status)


if __name__ == "__main__":
    unittest.main()
