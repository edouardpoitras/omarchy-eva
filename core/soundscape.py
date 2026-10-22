"""Acoustic earcon soundscape engine for Eva desktop automation suite.

Generates and plays subtle, elegant acoustic cues (<5ms latency)
via PipeWire pw-play on key voice lifecycle events.
"""

import os
import subprocess
import threading
from typing import Optional

from core.config import eva_config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(REPO_ROOT, "assets", "sounds")
os.makedirs(SOUNDS_DIR, exist_ok=True)


def generate_default_earcons(overwrite: bool = False):
    """Synthesize high-fidelity 48kHz audio earcons with soft, elegant amplitude."""
    listening_path = os.path.join(SOUNDS_DIR, "listening.wav")
    success_path = os.path.join(SOUNDS_DIR, "success.wav")
    deliberate_path = os.path.join(SOUNDS_DIR, "deliberate.wav")
    error_path = os.path.join(SOUNDS_DIR, "error.wav")

    if not overwrite and all(os.path.exists(p) for p in [listening_path, success_path, deliberate_path, error_path]):
        return

    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return

    sr = 48000

    # 1. Listening: Ascending dual-tone soft chime (523Hz C5 -> 784Hz G5)
    listening_path = os.path.join(SOUNDS_DIR, "listening.wav")
    if overwrite or not os.path.exists(listening_path):
        t1 = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
        w1 = 0.18 * np.sin(2 * np.pi * 523 * t1) + 0.08 * np.sin(2 * np.pi * 1046 * t1)
        env1 = np.exp(-15 * t1)
        part1 = w1 * env1

        t2 = np.linspace(0, 0.22, int(sr * 0.22), endpoint=False)
        w2 = 0.20 * np.sin(2 * np.pi * 784 * t2) + 0.10 * np.sin(2 * np.pi * 1568 * t2) + 0.05 * np.sin(2 * np.pi * 2352 * t2)
        env2 = np.exp(-12 * t2)
        part2 = w2 * env2

        chime = np.concatenate([part1, part2])
        sf.write(listening_path, chime.astype(np.float32), sr)

    # 2. Success: Crisp metallic affirmative ping (1046Hz -> 1318Hz)
    success_path = os.path.join(SOUNDS_DIR, "success.wav")
    if overwrite or not os.path.exists(success_path):
        t = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
        w = 0.25 * np.sin(2 * np.pi * 1046 * t) + 0.15 * np.sin(2 * np.pi * 1318 * t) + 0.08 * np.sin(2 * np.pi * 2093 * t)
        env = np.exp(-18 * t)
        sf.write(success_path, (w * env).astype(np.float32), sr)

    # 3. Deliberating: Subtle low-frequency resonant hum (110Hz -> 165Hz)
    deliberate_path = os.path.join(SOUNDS_DIR, "deliberate.wav")
    if overwrite or not os.path.exists(deliberate_path):
        t = np.linspace(0, 0.35, int(sr * 0.35), endpoint=False)
        w = 0.20 * np.sin(2 * np.pi * 110 * t) + 0.12 * np.sin(2 * np.pi * 165 * t) + 0.06 * np.sin(2 * np.pi * 220 * t)
        env = np.sin(np.pi * (t / 0.35)) * np.exp(-4 * t)
        sf.write(deliberate_path, (w * env).astype(np.float32), sr)

    # 4. Error: Soft descending warning double tone (440Hz -> 330Hz)
    error_path = os.path.join(SOUNDS_DIR, "error.wav")
    if overwrite or not os.path.exists(error_path):
        t1 = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
        w1 = 0.20 * np.sin(2 * np.pi * 440 * t1) + 0.10 * np.sin(2 * np.pi * 880 * t1)
        part1 = w1 * np.exp(-14 * t1)

        t2 = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
        w2 = 0.22 * np.sin(2 * np.pi * 330 * t2) + 0.10 * np.sin(2 * np.pi * 660 * t2)
        part2 = w2 * np.exp(-10 * t2)

        pause = np.zeros(int(sr * 0.03), dtype=np.float32)
        err = np.concatenate([part1, pause, part2])
        sf.write(error_path, err.astype(np.float32), sr)


class Soundscape:
    """Non-blocking acoustic soundscape controller."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        generate_default_earcons(overwrite=False)
        self.player_bin = "pw-play" if subprocess.run(["which", "pw-play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0 else "aplay"

    def play(self, name: str, volume: Optional[float] = None):
        """Play named acoustic earcon asynchronously via PipeWire."""
        if not self.enabled or not eva_config.get("sound_effects", True):
            return

        wav_path = os.path.join(SOUNDS_DIR, f"{name}.wav")
        if not os.path.exists(wav_path):
            return

        vol = volume if volume is not None else eva_config.earcon_volume

        def _play():
            try:
                cmd = [self.player_bin]
                if self.player_bin == "pw-play":
                    cmd.extend(["--volume", str(max(0.0, min(1.0, vol)))])
                cmd.append(wav_path)

                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                )
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

    def listening(self):
        """Play listening activation earcon."""
        self.play("listening")

    def success(self):
        """Play affirmative execution earcon."""
        self.play("success")

    def deliberating(self):
        """Play deliberating resonance hum."""
        self.play("deliberate")

    def error(self):
        """Play error warning earcon."""
        self.play("error")
