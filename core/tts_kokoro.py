"""Kokoro-82M Neural Text-to-Speech Engine for Eva desktop automation suite.

Provides ultra-fast local neural speech synthesis (<35ms on RTX 4090)
and direct playback via PipeWire (pw-play).
"""

import hashlib
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

from core.config import eva_config

# Cache directory for speech waveforms
AUDIO_CACHE_DIR = os.path.expanduser("~/.cache/eva/tts")
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# Default voice settings
DEFAULT_VOICE = "bf_emma"  # British female (Eva aesthetic)
SAMPLE_RATE = 24000

AVAILABLE_VOICES = {
    "bf_emma": {"name": "Emma", "gender": "female", "lang": "b", "accent": "British"},
    "bf_isabella": {"name": "Isabella", "gender": "female", "lang": "b", "accent": "British"},
    "af_bella": {"name": "Bella", "gender": "female", "lang": "a", "accent": "American"},
    "af_nicole": {"name": "Nicole", "gender": "female", "lang": "a", "accent": "American"},
    "af_sarah": {"name": "Sarah", "gender": "female", "lang": "a", "accent": "American"},
    "af_sky": {"name": "Sky", "gender": "female", "lang": "a", "accent": "American"},
    "bm_george": {"name": "George", "gender": "male", "lang": "b", "accent": "British"},
    "bm_lewis": {"name": "Lewis", "gender": "male", "lang": "b", "accent": "British"},
    "am_adam": {"name": "Adam", "gender": "male", "lang": "a", "accent": "American"},
    "am_michael": {"name": "Michael", "gender": "male", "lang": "a", "accent": "American"},
}


class KokoroTTS:
    """Local Kokoro-82M neural speech synthesis and playback controller."""

    def __init__(
        self,
        default_voice: Optional[str] = None,
        device: Optional[str] = None,
        lazy_init: bool = False,
    ):
        self._default_voice = default_voice
        self.device = device
        self._pipelines: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._current_player: Optional[subprocess.Popen] = None
        self._current_thread: Optional[threading.Thread] = None
        self._player_lock = threading.Lock()

        if not lazy_init:
            self._ensure_pipeline(self._lang_for_voice(self.default_voice))

    @property
    def default_voice(self) -> str:
        if self._default_voice:
            return self._default_voice
        return eva_config.voice

    def _lang_for_voice(self, voice: str) -> str:
        """Infer language code ('a' for American, 'b' for British) from voice identifier."""
        if voice in AVAILABLE_VOICES:
            return AVAILABLE_VOICES[voice]["lang"]
        if voice.startswith("b"):
            return "b"
        return "a"

    def _ensure_pipeline(self, lang_code: str):
        """Lazy-load KPipeline for the requested language code."""
        with self._lock:
            if lang_code in self._pipelines:
                return self._pipelines[lang_code]

            try:
                import torch
                from kokoro import KPipeline

                if self.device is None:
                    self.device = "cuda" if torch.cuda.is_available() else "cpu"

                pipeline = KPipeline(lang_code=lang_code, device=self.device)
                self._pipelines[lang_code] = pipeline
                return pipeline
            except Exception as e:
                print(f"Warning: Failed to initialize Kokoro pipeline ({lang_code}): {e}")
                return None

    def get_cache_path(self, text: str, voice: str, speed: float) -> str:
        """Compute disk cache path for a given utterance."""
        slug = f"{voice}_{speed:.2f}_{text.strip()}".encode("utf-8")
        h = hashlib.sha256(slug).hexdigest()[:16]
        return os.path.join(AUDIO_CACHE_DIR, f"speech_{h}.wav")

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Tuple[Optional[Any], float]:
        """Synthesize text into a float32 audio waveform.
        
        Returns:
            Tuple of (audio_waveform, synthesis_latency_ms)
        """
        text = text.strip()
        if not text:
            return None, 0.0

        v = voice or self.default_voice
        sp = speed if speed is not None else float(eva_config.get("voice_speed", 1.0))
        lang = self._lang_for_voice(v)
        pipe = self._ensure_pipeline(lang)
        if not pipe:
            return None, 0.0

        t0 = time.perf_counter()
        try:
            chunks = []
            generator = pipe(text, voice=v, speed=sp)
            for res in generator:
                if hasattr(res, "audio") and res.audio is not None:
                    audio_chunk = res.audio
                    if hasattr(audio_chunk, "cpu"):
                        audio_chunk = audio_chunk.cpu().numpy()
                    chunks.append(audio_chunk)

            if not chunks:
                return None, 0.0

            if len(chunks) == 1:
                audio = chunks[0]
            elif np is not None:
                audio = np.concatenate(chunks)
            else:
                audio = chunks[0]
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return audio, latency_ms
        except Exception as e:
            print(f"Error synthesizing speech with Kokoro: {e}")
            return None, 0.0

    def synthesize_to_file(
        self,
        text: str,
        output_wav: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Tuple[Optional[str], float]:
        """Synthesize text and write directly to a WAV file."""
        import soundfile as sf

        v = voice or self.default_voice
        sp = speed if speed is not None else float(eva_config.get("voice_speed", 1.0))
        cache_path = self.get_cache_path(text, v, sp)

        # Check existing cache
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1024:
            dest = output_wav or cache_path
            if dest != cache_path:
                import shutil
                shutil.copyfile(cache_path, dest)
            return dest, 0.5  # Instant cache hit

        target_file = output_wav or cache_path
        audio, latency_ms = self.synthesize(text, voice=v, speed=sp)
        if audio is None:
            return None, latency_ms

        sf.write(target_file, audio, SAMPLE_RATE)
        # Also persist to cache if a custom target was specified
        if target_file != cache_path:
            import shutil
            shutil.copyfile(target_file, cache_path)

        return target_file, latency_ms

    def stop_playback(self):
        """Immediately terminate any currently playing voice audio."""
        with self._player_lock:
            if self._current_player and self._current_player.poll() is None:
                try:
                    self._current_player.terminate()
                    self._current_player.wait(timeout=0.2)
                except Exception:
                    try:
                        self._current_player.kill()
                    except Exception:
                        pass
                self._current_player = None
            thread = self._current_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)

    def wait_for_playback(self, timeout: Optional[float] = None) -> bool:
        """Wait for any active background playback thread to finish."""
        with self._player_lock:
            thread = self._current_thread
        if thread and thread.is_alive():
            try:
                thread.join(timeout=timeout)
            except KeyboardInterrupt:
                self.stop_playback()
                raise
            return not thread.is_alive()
        return True

    def speak(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        block: bool = False,
    ) -> Dict[str, Any]:
        """Synthesize text and play immediately via PipeWire / pw-play.
        
        Args:
            text: Text to speak.
            voice: Voice ID (default: eva_config.voice / 'bf_emma').
            speed: Speech rate multiplier.
            block: If True, waits until playback finishes. If False, plays asynchronously.
            
        Returns:
            Dictionary with status, latency_ms, audio_duration_sec, and wav_path.
        """
        if eva_config.verbosity == "silent":
            return {
                "success": True,
                "latency_ms": 0.0,
                "duration_sec": 0.0,
                "voice": voice or self.default_voice,
                "wav_path": None,
                "silent": True,
            }

        wav_path, latency_ms = self.synthesize_to_file(
            text, voice=voice, speed=speed
        )

        if not wav_path or not os.path.exists(wav_path):
            return {
                "success": False,
                "error": "Failed to synthesize audio",
                "latency_ms": latency_ms,
            }

        # Calculate audio duration
        duration_sec = 0.0
        try:
            import soundfile as sf
            info = sf.info(wav_path)
            duration_sec = round(info.duration, 2)
        except Exception:
            pass

        # Stop previous playback before starting new
        self.stop_playback()

        # Find best playback binary (pw-play -> paplay -> aplay)
        player_bin = None
        for cmd in ["pw-play", "paplay", "aplay"]:
            if subprocess.run(["which", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                player_bin = cmd
                break

        if not player_bin:
            return {
                "success": False,
                "error": "No audio player found (pw-play, paplay, aplay)",
                "latency_ms": latency_ms,
                "wav_path": wav_path,
            }

        def _play():
            with self._player_lock:
                proc = subprocess.Popen(
                    [player_bin, wav_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._current_player = proc

            try:
                proc.wait()
            except Exception:
                pass
            finally:
                with self._player_lock:
                    if self._current_player is proc:
                        self._current_player = None

        if block:
            _play()
        else:
            t = threading.Thread(target=_play, daemon=True)
            with self._player_lock:
                self._current_thread = t
            t.start()

        return {
            "success": True,
            "latency_ms": latency_ms,
            "duration_sec": duration_sec,
            "voice": voice or self.default_voice,
            "wav_path": wav_path,
        }

    def list_voices(self) -> Dict[str, Any]:
        """Return available voices and current default."""
        return {
            "default": self.default_voice,
            "voices": AVAILABLE_VOICES,
        }
