"""Voxtype speech recognition bridge for Omarchy Linux."""

import os
import shutil
import subprocess
import time
from typing import Callable, Optional


class VoxtypeBridge:
    """Manages audio recording and transcription handoff via Voxtype."""

    TRANSCRIPTION_PATH = "/dev/shm/eva_transcription.txt"

    def __init__(self, on_state_changed: Optional[Callable[[str], None]] = None):
        self.on_state_changed = on_state_changed
        self.runtime_dir = os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"
        )
        self.state_file = os.path.join(self.runtime_dir, "voxtype", "state")
        self.has_voxtype = shutil.which("voxtype") is not None

    def get_daemon_state(self) -> str:
        """Read Voxtype daemon state ('idle', 'recording', 'transcribing')."""
        if not os.path.exists(self.state_file):
            return "idle"
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return f.read().strip() or "idle"
        except Exception:
            return "idle"

    def is_recording(self) -> bool:
        """Check if Voxtype is currently recording audio."""
        return self.get_daemon_state() == "recording"

    def start_recording(self, output_file: str = TRANSCRIPTION_PATH) -> bool:
        """Signal Voxtype to begin recording speech, directing output to target file."""
        if not self.has_voxtype:
            return False

        # Clean up any stale transcription file
        if os.path.exists(output_file):
            try:
                os.remove(output_file)
            except OSError:
                pass

        try:
            res = subprocess.run(
                ["voxtype", "record", "start", f"--file={output_file}", "--no-osd"],
                capture_output=True,
                timeout=1.5,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    def stop_recording(self) -> bool:
        """Signal Voxtype to stop recording and trigger transcription."""
        if not self.has_voxtype:
            return False

        try:
            res = subprocess.run(
                ["voxtype", "record", "stop"],
                capture_output=True,
                timeout=1.5,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    def toggle_recording(self, output_file: str = TRANSCRIPTION_PATH) -> bool:
        """Toggle recording state: start if idle, stop if recording."""
        if self.is_recording():
            return self.stop_recording()
        return self.start_recording(output_file)

    def wait_for_transcription(
        self,
        output_file: str = TRANSCRIPTION_PATH,
        timeout_sec: float = 8.0,
        poll_interval: float = 0.05,
    ) -> Optional[str]:
        """Wait for Voxtype to complete Whisper transcription and return recognized text."""
        start_time = time.perf_counter()

        # Phase 1: Wait until Voxtype transitions to transcribing or output file appears
        while (time.perf_counter() - start_time) < timeout_sec:
            # Check if output file was written and non-empty
            if os.path.exists(output_file):
                try:
                    with open(output_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        # Clean up file once read
                        try:
                            os.remove(output_file)
                        except OSError:
                            pass
                        return content
                except Exception:
                    pass

            state = self.get_daemon_state()
            # If state returns to idle and output file still doesn't exist, transcription finished
            if state == "idle" and (time.perf_counter() - start_time) > 0.5:
                # One last check
                if os.path.exists(output_file):
                    try:
                        with open(output_file, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                        os.remove(output_file)
                        return content
                    except Exception:
                        pass
                break

            time.sleep(poll_interval)

        return None
