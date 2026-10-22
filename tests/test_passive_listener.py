"""Unit tests for PassiveListener, Wake Word handling, and Conversational Follow-Up Mode."""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.config import eva_config
from core.dispatcher import CommandDispatcher
from core.passive_listener import PassiveListener


class TestPassiveListener(unittest.TestCase):
    """Test suite covering streaming wake word, dispatcher wake phrase stripping, and follow-up mode."""

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
        # Save original config
        self._orig_wake_word = eva_config.get("wake_word_enabled", True)
        self._orig_follow_up = eva_config.get("follow_up_mode", True)
        self._orig_turns = eva_config.get("max_follow_up_turns", 4)

    def tearDown(self):
        eva_config.set("wake_word_enabled", self._orig_wake_word)
        eva_config.set("follow_up_mode", self._orig_follow_up)
        eva_config.set("max_follow_up_turns", self._orig_turns)

    # 1. Dispatcher Wake Phrase Stripping Tests
    def test_wake_phrase_stripping_single_breath(self):
        """Test that single-breath commands with leading wake words strip cleanly and match reflexes."""
        cases = [
            ("Eva, what time is it", "time_date"),
            ("Hey Eva, what time is it", "time_date"),
            ("hey eva pause music", "pause"),
            ("ok eva, pause music", "pause"),
            ("hello eva switch to workspace 2", "workspace 2"),
            ("okay eva, repeat that", "repeat_statement"),
        ]
        for phrase, expected_action in cases:
            with self.subTest(phrase=phrase):
                res = self.dispatcher.dispatch_text(phrase, execute=False)
                self.assertTrue(res.get("matched"), f"Failed to match: {phrase}")
                self.assertEqual(res.get("action"), expected_action)

    def test_wake_word_summon(self):
        """Test saying 'Eva' or 'Hey Eva' alone triggers WAKE_WORD_SUMMON intent."""
        for phrase in ("eva", "Eva", "hey eva", "Hey Eva", "ok eva", "hello eva"):
            with self.subTest(phrase=phrase):
                res = self.dispatcher.dispatch_text(phrase, execute=False)
                self.assertTrue(res.get("matched"))
                self.assertEqual(res.get("intent"), "WAKE_WORD_SUMMON")
                self.assertEqual(res.get("action"), "await_command")

    def test_dismissal_reflex(self):
        """Test conversational dismissal triggers DISMISS_FOLLOW_UP intent."""
        dismiss_phrases = [
            "never mind",
            "nevermind",
            "dismiss",
            "cancel",
            "stop listening",
            "go to sleep",
            "goodbye",
            "bye eva",
            "that's all",
            "that is all",
        ]
        for phrase in dismiss_phrases:
            with self.subTest(phrase=phrase):
                res = self.dispatcher.dispatch_text(phrase, execute=False)
                self.assertTrue(res.get("matched"), f"Failed to match: {phrase}")
                self.assertEqual(res.get("intent"), "DISMISS_FOLLOW_UP")
                self.assertEqual(res.get("action"), "dismiss_follow_up")

    # 2. PassiveListener State & Lifecycle Tests
    @patch("core.passive_listener.HAS_AUDIO_DEPS", True)
    @patch("os.path.exists", return_value=True)
    def test_passive_listener_availability(self, mock_exists):
        """Test that KWS model files in ~/.local/share/eva/models/kws are detected."""
        listener = PassiveListener()
        self.assertTrue(listener.is_available())

    def test_follow_up_turn_management(self):
        """Test that follow-up mode increments turn count up to maximum allowed turns."""
        listener = PassiveListener()
        listener.running = True
        eva_config.set("max_follow_up_turns", 3)

        self.assertFalse(listener.follow_up_active)
        self.assertEqual(listener.follow_up_turns, 0)

        # Turn 1
        listener.start_follow_up()
        self.assertTrue(listener.follow_up_active)
        self.assertEqual(listener.follow_up_turns, 1)
        self.assertEqual(listener.state, "follow_up")

        # Turn 2
        listener.start_follow_up()
        self.assertTrue(listener.follow_up_active)
        self.assertEqual(listener.follow_up_turns, 2)

        # Turn 3
        listener.start_follow_up()
        self.assertTrue(listener.follow_up_active)
        self.assertEqual(listener.follow_up_turns, 3)

        # Turn 4 (Exceeds max_turns=3, should automatically reset)
        listener.start_follow_up()
        self.assertFalse(listener.follow_up_active)
        self.assertEqual(listener.follow_up_turns, 0)
        self.assertEqual(listener.state, "listening_wake_word")

    def test_wake_word_spotted_callback(self):
        """Test that detecting a wake word transitions state and invokes callback."""
        mock_cb = MagicMock()
        listener = PassiveListener(on_wake_word=mock_cb)

        # Seed ring buffer with dummy samples
        for _ in range(int(16000 * 2.0)):
            listener.ring_buffer.append(0.01)

        listener._handle_wake_word_spotted("EVA")
        self.assertEqual(listener.state, "recording_command")
        self.assertGreater(len(listener.command_frames), 0)

    def test_speech_onset_in_follow_up(self):
        """Test that speech detected in follow-up mode cancels follow-up and begins recording."""
        mock_cb = MagicMock()
        listener = PassiveListener(on_speech_started=mock_cb)
        listener.follow_up_active = True
        listener.state = "follow_up"

        listener._handle_speech_onset_in_follow_up()
        self.assertFalse(listener.follow_up_active)
        self.assertEqual(listener.state, "recording_command")

    # 3. Call Detection Safeguard
    @patch("subprocess.run")
    def test_call_detection_suspends_passive_triggers(self, mock_run):
        """Test that active VoIP calls in PipeWire mark is_call_active."""
        mock_res = MagicMock()
        mock_res.stdout = "Client: application.name = 'Discord'\nmedia.class = 'Stream/Input/Audio'"
        mock_run.return_value = mock_res

        listener = PassiveListener()
        listener.running = True
        listener._schedule_call_check()

        self.assertTrue(listener.is_call_active)
        listener.stop()


if __name__ == "__main__":
    unittest.main()
