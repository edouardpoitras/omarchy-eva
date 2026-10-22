"""Unit tests for Phase 5 (Soundscape & HUD Earcons)."""

import os
import unittest
import wave
from unittest.mock import MagicMock, patch

from core.soundscape import SOUNDS_DIR, Soundscape, generate_default_earcons


class TestSoundscape(unittest.TestCase):
    """Test suite for Acoustic Earcons and Soundscape engine."""

    def setUp(self):
        generate_default_earcons()
        self.sound = Soundscape(enabled=True)

    def test_earcon_files_generated(self):
        expected_sounds = ["listening.wav", "success.wav", "deliberate.wav", "error.wav"]
        for sound in expected_sounds:
            p = os.path.join(SOUNDS_DIR, sound)
            self.assertTrue(os.path.exists(p), f"Sound file {sound} was not generated")
            self.assertGreater(os.path.getsize(p), 1000)

            # Validate WAV format and sample rate
            with wave.open(p, "rb") as wf:
                self.assertEqual(wf.getframerate(), 48000)
                duration = wf.getnframes() / float(wf.getframerate())
                self.assertGreater(duration, 0.05)

    def test_play_non_blocking(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            self.sound.listening()
            self.sound.success()
            self.sound.deliberating()
            self.sound.error()

    def test_disabled_soundscape(self):
        disabled_sound = Soundscape(enabled=False)
        with patch("subprocess.run") as mock_run:
            disabled_sound.play("listening")
            mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
