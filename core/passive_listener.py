"""Passive audio listener with streaming wake word detection and conversational follow-up mode."""

import collections
import os
import re
import subprocess
import threading
import time
import wave
from typing import Any, Callable, Dict, List, Optional

from core.config import eva_config

try:
    import numpy as np
    import sherpa_onnx
    import sounddevice as sd
    HAS_AUDIO_DEPS = True
except ImportError:
    HAS_AUDIO_DEPS = False
    np = None


class PassiveListener:
    """Continuously monitors microphone for wake words and handles follow-up listening windows."""

    KWS_DIR = os.path.expanduser("~/.local/share/eva/models/kws")
    CMD_WAV_PATH = "/dev/shm/eva_passive_cmd.wav"

    def __init__(
        self,
        on_wake_word: Optional[Callable[[], None]] = None,
        on_speech_started: Optional[Callable[[], None]] = None,
        on_command_audio: Optional[Callable[[str], None]] = None,
        on_follow_up_expired: Optional[Callable[[], None]] = None,
        on_state_changed: Optional[Callable[[str], None]] = None,
    ):
        self.on_wake_word = on_wake_word
        self.on_speech_started = on_speech_started
        self.on_command_audio = on_command_audio
        self.on_follow_up_expired = on_follow_up_expired
        self.on_state_changed = on_state_changed

        self.running = False
        self.stream: Optional[Any] = None
        self.kws: Optional[Any] = None
        self.kws_stream: Optional[Any] = None

        # Audio settings (16kHz mono float32)
        self.sample_rate = 16000
        self.chunk_size = 512  # 32ms per chunk

        # Rolling ring buffer for pre-trigger audio (2.0 seconds)
        self.ring_buffer: collections.deque = collections.deque(
            maxlen=int(self.sample_rate * 2.0)
        )

        # State tracking: "idle", "listening_wake_word", "recording_command", "follow_up"
        self.state = "idle"
        self._lock = threading.RLock()

        # Command recording buffer
        self.command_frames: List[np.ndarray] = []
        self.last_speech_time = 0.0
        self.speech_frames_count = 0
        self.record_start_time = 0.0

        # Follow-up mode state
        self.follow_up_active = False
        self.follow_up_start_time = 0.0
        self.follow_up_turns = 0

        # Call-state safeguard
        self.is_call_active = False
        self._call_check_timer: Optional[threading.Timer] = None
        self._worker_thread: Optional[threading.Thread] = None

        # VAD thresholds
        self.speech_energy_threshold = 0.015
        self.silence_timeout_sec = 0.8
        self.max_recording_sec = 10.0

    def is_available(self) -> bool:
        """Check if necessary libraries and KWS model files are present."""
        if not HAS_AUDIO_DEPS:
            return False
        tokens_file = os.path.join(self.KWS_DIR, "tokens.txt")
        encoder_file = os.path.join(
            self.KWS_DIR, "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
        )
        return os.path.exists(tokens_file) and os.path.exists(encoder_file)

    def _ensure_keywords_file(self) -> str:
        """Ensure keywords file with BPE tokens exists."""
        keywords_file = os.path.join(self.KWS_DIR, "eva_keywords.txt")
        if not os.path.exists(keywords_file):
            os.makedirs(self.KWS_DIR, exist_ok=True)
            with open(keywords_file, "w", encoding="utf-8") as f:
                f.write("▁E V A\n")
                f.write("▁HE Y ▁E V A\n")
                f.write("▁O K ▁E V A\n")
        return keywords_file

    def _init_kws(self) -> bool:
        """Initialize sherpa-onnx KeywordSpotter."""
        if not self.is_available():
            return False

        try:
            keywords_file = self._ensure_keywords_file()
            self.kws = sherpa_onnx.KeywordSpotter(
                tokens=os.path.join(self.KWS_DIR, "tokens.txt"),
                encoder=os.path.join(
                    self.KWS_DIR, "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
                ),
                decoder=os.path.join(
                    self.KWS_DIR, "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"
                ),
                joiner=os.path.join(
                    self.KWS_DIR, "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"
                ),
                keywords_file=keywords_file,
                num_threads=2,
                provider="cpu",
            )
            self.kws_stream = self.kws.create_stream()
            return True
        except Exception as e:
            print(f"[PassiveListener] Error initializing KeywordSpotter: {e}")
            return False

    def start(self) -> bool:
        """Start passive listener audio thread."""
        with self._lock:
            if self.running:
                return True

            if not self._init_kws():
                return False

            self.running = True
            self.state = "listening_wake_word"

            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=self.chunk_size,
                    callback=self._audio_callback,
                )
                self.stream.start()
            except Exception as e:
                print(f"[PassiveListener] Failed to start audio input stream: {e}")
                self.running = False
                return False

            # Start call-state watcher
            self._schedule_call_check()
            return True

    def stop(self):
        """Stop passive listener and clean up resources."""
        with self._lock:
            self.running = False
            self.state = "idle"
            self.follow_up_active = False

            if self._call_check_timer:
                self._call_check_timer.cancel()
                self._call_check_timer = None

            if self.stream:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

            self.kws = None
            self.kws_stream = None

    def start_follow_up(self, timeout_sec: Optional[float] = None):
        """Trigger conversational follow-up window after a command completes."""
        with self._lock:
            if not self.running:
                return

            max_turns = eva_config.get("max_follow_up_turns", 4)
            if self.follow_up_turns >= max_turns:
                self.reset_follow_up()
                return

            self.follow_up_active = True
            self.follow_up_start_time = time.time()
            self.follow_up_turns += 1
            self.state = "follow_up"

    def reset_follow_up(self):
        """Cancel follow-up mode and return to listening for wake word."""
        with self._lock:
            self.follow_up_active = False
            self.follow_up_turns = 0
            if self.running:
                self.state = "listening_wake_word"
            else:
                self.state = "idle"

    def _schedule_call_check(self):
        """Check PipeWire for active VoIP recording streams periodically."""
        if not self.running:
            return

        def _check():
            try:
                res = subprocess.run(
                    ["pactl", "list", "source-outputs"],
                    capture_output=True,
                    text=True,
                    timeout=0.6,
                    check=False,
                )
                txt = res.stdout.lower()
                # Check for known calling / conferencing clients
                active = any(
                    client in txt
                    for client in (
                        "discord",
                        "zoom",
                        "slack",
                        "skype",
                        "teams",
                        "webex",
                        "mumble",
                    )
                )
                self.is_call_active = active
            except Exception:
                pass

            if self.running:
                self._call_check_timer = threading.Timer(2.5, self._schedule_call_check)
                self._call_check_timer.daemon = True
                self._call_check_timer.start()

        _check()

    def _audio_callback(self, indata, frames, time_info, status):
        """Real-time audio callback invoked by PortAudio."""
        if not self.running or indata is None:
            return

        # Squeeze mono audio to 1D float32 array
        samples = indata[:, 0].copy()

        # Update rolling pre-trigger buffer
        self.ring_buffer.extend(samples)

        # If a VoIP call is active, suspend passive triggers
        if self.is_call_active:
            return

        with self._lock:
            cur_state = self.state

        # State 1: Listening for Wake Word ("Eva" / "Hey Eva")
        if cur_state == "listening_wake_word":
            if not eva_config.get("wake_word_enabled", True):
                return

            if self.kws and self.kws_stream:
                self.kws_stream.accept_waveform(self.sample_rate, samples)
                if self.kws.is_ready(self.kws_stream):
                    self.kws.decode_stream(self.kws_stream)
                    result = self.kws.get_result(self.kws_stream)
                    if result:
                        self.kws.reset_stream(self.kws_stream)
                        self._handle_wake_word_spotted(result)

        # State 2: Follow-Up Mode (Mic open awaiting follow-up speech)
        elif cur_state == "follow_up":
            # Check timeout
            timeout = eva_config.get("follow_up_timeout_sec", 8.0)
            if (time.time() - self.follow_up_start_time) > timeout:
                self.reset_follow_up()
                if self.on_follow_up_expired:
                    self.on_follow_up_expired()
                return

            # VAD energy detection for speech onset
            rms = np.sqrt(np.mean(samples**2))
            if rms > self.speech_energy_threshold:
                self._handle_speech_onset_in_follow_up()

        # State 3: Recording Spoken Command
        elif cur_state == "recording_command":
            self.command_frames.append(samples)
            rms = np.sqrt(np.mean(samples**2))

            if rms > self.speech_energy_threshold:
                self.last_speech_time = time.time()
                self.speech_frames_count += len(samples)

            now = time.time()
            # Silence detected after speech
            is_silent = (now - self.last_speech_time) > self.silence_timeout_sec
            has_min_speech = self.speech_frames_count > int(self.sample_rate * 0.35)
            is_max_duration = (now - self.record_start_time) > self.max_recording_sec

            if (is_silent and has_min_speech) or is_max_duration:
                self._finalize_command_recording()

    def _handle_wake_word_spotted(self, keyword: str):
        """Wake word was spotted: transition to recording command."""
        with self._lock:
            self.state = "recording_command"
            self.record_start_time = time.time()
            self.last_speech_time = time.time()
            self.speech_frames_count = int(self.sample_rate * 0.4)

            # Pre-seed command buffer with the last 1.2 seconds from the ring buffer
            # so the wake word and any trailing words spoken in the same breath are preserved
            pre_samples = list(self.ring_buffer)[-int(self.sample_rate * 1.2) :]
            self.command_frames = [np.array(pre_samples, dtype=np.float32)] if np is not None else [pre_samples]

        if self.on_wake_word:
            # Dispatch to worker thread to avoid blocking PortAudio callback
            threading.Thread(target=self.on_wake_word, daemon=True).start()

    def _handle_speech_onset_in_follow_up(self):
        """Speech onset detected during follow-up mode."""
        with self._lock:
            self.state = "recording_command"
            self.follow_up_active = False
            self.record_start_time = time.time()
            self.last_speech_time = time.time()
            self.speech_frames_count = int(self.sample_rate * 0.2)

            # Pre-seed with recent 0.3s of audio to avoid dropping first consonant
            pre_samples = list(self.ring_buffer)[-int(self.sample_rate * 0.3) :]
            self.command_frames = [np.array(pre_samples, dtype=np.float32)] if np is not None else [pre_samples]

        if self.on_speech_started:
            threading.Thread(target=self.on_speech_started, daemon=True).start()

    def _finalize_command_recording(self):
        """User finished speaking: write WAV and invoke handoff callback."""
        with self._lock:
            self.state = "listening_wake_word"
            frames = list(self.command_frames)
            self.command_frames = []

        if not frames:
            return

        def _save_and_dispatch():
            try:
                # Concatenate all float32 samples
                audio = np.concatenate(frames)
                # Convert float32 [-1.0, 1.0] to int16 PCM
                audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

                with wave.open(self.CMD_WAV_PATH, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(audio_int16.tobytes())

                if self.on_command_audio:
                    self.on_command_audio(self.CMD_WAV_PATH)
            except Exception as e:
                print(f"[PassiveListener] Error saving command audio: {e}")

        threading.Thread(target=_save_and_dispatch, daemon=True).start()
