"""Unit tests for Jarvis daemon state persistence, HUD coordination, and IPC requests."""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.daemon import JarvisDaemon


class TestJarvisDaemon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.socket_path = os.path.join(self.temp_dir, "test_ipc.sock")
        self.state_dir = os.path.join(self.temp_dir, "jarvis")
        os.makedirs(self.state_dir, exist_ok=True)

        # Patch paths to isolate inside temporary directory
        self.env_patcher = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp_dir})
        self.env_patcher.start()

        self.daemon = JarvisDaemon(socket_path=self.socket_path)
        self.daemon.sound = MagicMock()
        self.daemon.tts = MagicMock()
        self.daemon.voxtype = MagicMock()
        self.daemon.input = MagicMock()
        self.daemon.vision = MagicMock()

    def tearDown(self):
        self.env_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_json_persistence(self):
        """Verify set_state writes state.json atomically with required fields."""
        state_file = os.path.join(self.daemon.jarvis_dir, "state.json")
        self.daemon.set_state(
            "executing",
            command="switch to workspace 2",
            action="workspace 2",
            intent="HYPR_WORKSPACE",
            confidence=0.98,
        )

        self.assertTrue(os.path.exists(state_file))
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["state"], "executing")
        self.assertEqual(data["command"], "switch to workspace 2")
        self.assertEqual(data["action"], "workspace 2")
        self.assertEqual(data["intent"], "HYPR_WORKSPACE")
        self.assertEqual(data["confidence"], 0.98)
        self.assertIn("timestamp", data)

    def test_get_status_request(self):
        """Verify get_status returns current state and results."""
        self.daemon.set_state("listening", command="hello")
        resp = self.daemon.handle_request({"action": "get_status"})
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["state"], "listening")
        self.assertEqual(resp["last_command"], "hello")

    def test_execute_text_dispatch(self):
        """Verify execute_text sets state and returns dispatch result."""
        self.daemon.dispatcher.dispatch_text = MagicMock(
            return_value={
                "matched": True,
                "action": "workspace 3",
                "intent": "HYPR_WORKSPACE",
                "success": True,
                "confidence": 1.0,
            }
        )

        resp = self.daemon.handle_request({"action": "execute_text", "text": "switch to workspace 3"})
        self.assertEqual(resp["status"], "ok")
        self.assertTrue(resp["result"]["success"])
        self.assertEqual(self.daemon.last_command, "switch to workspace 3")
        self.daemon.sound.success.assert_called_once()

    def test_demo_hud_action(self):
        """Verify demo_hud triggers soundscape and returns ok."""
        resp = self.daemon.handle_request({"action": "demo_hud"})
        self.assertEqual(resp["status"], "ok")
        self.assertIn("running", resp["message"])


if __name__ == "__main__":
    unittest.main()
