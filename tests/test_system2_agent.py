"""Unit tests for Phase 3 (System 2 Agent & Kokoro TTS)."""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.dispatcher import CommandDispatcher
from core.system2_agent import System2Agent, strip_ansi_and_banners
from core.tts_kokoro import KokoroTTS


class TestKokoroTTS(unittest.TestCase):
    """Test suite for Kokoro-82M neural TTS."""

    def setUp(self):
        self.tts = KokoroTTS(lazy_init=True)

    def test_list_voices(self):
        voices = self.tts.list_voices()
        self.assertIn("default", voices)
        self.assertIn("voices", voices)
        self.assertIn("bm_george", voices["voices"])
        self.assertEqual(voices["voices"]["bm_george"]["lang"], "b")

    def test_cache_path_generation(self):
        path1 = self.tts.get_cache_path("Hello world", "bm_george", 1.0)
        path2 = self.tts.get_cache_path("Hello world", "bm_george", 1.0)
        path3 = self.tts.get_cache_path("Hello world", "am_adam", 1.0)
        self.assertEqual(path1, path2)
        self.assertNotEqual(path1, path3)
        self.assertTrue(path1.endswith(".wav"))

    def test_synthesize_mocked(self):
        # Test synthesis logic with mocked pipeline
        import numpy as np
        mock_pipe = MagicMock()
        mock_result = MagicMock()
        mock_result.audio = np.zeros(24000, dtype=np.float32)
        mock_pipe.return_value = [mock_result]

        with patch.object(self.tts, "_ensure_pipeline", return_value=mock_pipe):
            audio, latency_ms = self.tts.synthesize("Test speech", voice="bm_george")
            self.assertIsNotNone(audio)
            self.assertEqual(len(audio), 24000)
            self.assertGreaterEqual(latency_ms, 0.0)

    def test_wait_for_playback_no_thread(self):
        self.assertTrue(self.tts.wait_for_playback())

    def test_wait_for_playback_with_active_thread(self):
        import threading
        import time

        def worker():
            time.sleep(0.05)

        t = threading.Thread(target=worker)
        self.tts._current_thread = t
        t.start()
        self.assertTrue(t.is_alive())
        result = self.tts.wait_for_playback(timeout=1.0)
        self.assertTrue(result)
        self.assertFalse(t.is_alive())

    def test_stop_playback_joins_thread(self):
        import threading
        import time

        mock_player = MagicMock()
        mock_player.poll.return_value = None

        def worker():
            time.sleep(0.05)

        t = threading.Thread(target=worker)
        self.tts._current_player = mock_player
        self.tts._current_thread = t
        t.start()

        self.tts.stop_playback()
        mock_player.terminate.assert_called_once()
        self.assertFalse(t.is_alive())


class TestSystem2Agent(unittest.TestCase):
    """Test suite for System 2 Deliberative Reasoning Agent."""

    def setUp(self):
        self.agent = System2Agent(enable_tts=False)

    def test_agent_wait_for_playback(self):
        # Without TTS enabled
        self.assertTrue(self.agent.wait_for_playback())

        # With mocked TTS
        mock_tts = MagicMock()
        mock_tts.wait_for_playback.return_value = True
        self.agent.tts = mock_tts
        self.assertTrue(self.agent.wait_for_playback())
        mock_tts.wait_for_playback.assert_called_once()

    def test_strip_ansi_and_banners(self):
        raw = "\x1B[32mWarning: Basic terminal\x1B[0m\nYOLO mode is enabled.\n[STARTUP] log\nHello, sir! How may I help?"
        clean = strip_ansi_and_banners(raw)
        self.assertEqual(clean, "Hello, sir! How may I help?")

    def test_format_system_prompt(self):
        telemetry = {
            "active_window": {"title": "Terminal", "class": "foot", "workspace": "1"},
            "open_windows": [{"title": "Browser", "class": "brave", "workspace": "2"}],
            "workspaces": [{"id": 1, "name": "1", "windows": 1}],
        }
        prompt = self.agent.format_system_prompt(telemetry)
        self.assertIn("Terminal", prompt)
        self.assertIn("foot", prompt)
        self.assertIn("brave", prompt)
        self.assertIn("DO NOT use markdown formatting", prompt)

    def test_clarification_detection(self):
        self.agent.history.clear()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Which workspace did you want me to switch to?", stderr="")
            res = self.agent.query("switch workspace", speak=False)
            self.assertTrue(res["requires_clarification"])
            self.assertIn("Which workspace", res["response"])

    def test_conversation_history(self):
        self.agent.history.clear()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Affirmative.", stderr="")
            self.agent.query("Eva, status check", speak=False)
            self.assertEqual(len(self.agent.history), 2)
            self.assertEqual(self.agent.history[0]["role"], "user")
            self.assertEqual(self.agent.history[0]["content"], "Eva, status check")
            self.assertEqual(self.agent.history[1]["role"], "assistant")
            self.assertEqual(self.agent.history[1]["content"], "Affirmative.")


class TestDispatcherSystem2Escalation(unittest.TestCase):
    """Test suite for Dispatcher escalation into System 2."""

    def test_escalate_generative_calls_system2(self):
        mock_system2 = MagicMock()
        mock_system2.query.return_value = {
            "status": "ok",
            "agent": "gemini",
            "response": "The CPU temperature is 42 degrees Celsius.",
            "requires_clarification": False,
            "latency_ms": 150.0,
        }

        mock_laya = MagicMock()
        mock_laya.predict.return_value = {
            "available": True,
            "intent": "ESCALATE_GENERATIVE",
            "confidence": 0.98,
            "confident": True,
            "temperature": 0.1,
            "threshold": 0.85,
            "distribution": {"ESCALATE_GENERATIVE": 0.98},
            "latency_ms": 15.0,
        }

        dispatcher = CommandDispatcher(
            hypr=MagicMock(),
            media=MagicMock(),
            laya=mock_laya,
            system2=mock_system2,
        )

        res = dispatcher.dispatch_text("Eva, what is the temperature of the CPU?")
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "ESCALATE_GENERATIVE")
        self.assertEqual(res["action"], "system2_agent_query")
        self.assertEqual(res["response"], "The CPU temperature is 42 degrees Celsius.")
        mock_system2.query.assert_called_once()

    def test_unmatched_falls_back_to_system2(self):
        mock_system2 = MagicMock()
        mock_system2.query.return_value = {
            "status": "ok",
            "agent": "gemini",
            "response": "Certainly, I have noted that.",
            "requires_clarification": False,
            "latency_ms": 120.0,
        }

        mock_laya = MagicMock()
        mock_laya.predict.return_value = {
            "available": False,
            "intent": "UNKNOWN",
            "confidence": 0.1,
            "confident": False,
            "temperature": 1.0,
            "threshold": 0.85,
            "distribution": {},
            "latency_ms": 1.0,
        }

        dispatcher = CommandDispatcher(
            hypr=MagicMock(),
            media=MagicMock(),
            laya=mock_laya,
            system2=mock_system2,
        )

        res = dispatcher.dispatch_text("random query that matches no reflex rule")
        self.assertTrue(res["matched"])
        self.assertEqual(res["action"], "system2_agent_query")
        mock_system2.query.assert_called_once()


if __name__ == "__main__":
    unittest.main()
