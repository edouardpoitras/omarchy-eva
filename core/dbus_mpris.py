"""Media playback and PipeWire audio control wrapper for Omarchy desktop automation."""

import shutil
import subprocess
from typing import Dict, Optional


class DbusMediaControl:
    """Controls media playback and audio endpoints matching Omarchy native keybindings."""

    def __init__(self):
        self.has_omarchy_shell = shutil.which("omarchy-shell") is not None
        self.has_playerctl = shutil.which("playerctl") is not None
        self.has_wpctl = shutil.which("wpctl") is not None
        self.has_omarchy_vol = shutil.which("omarchy-audio-output-volume") is not None
        self.has_omarchy_mic = shutil.which("omarchy-audio-input-mute") is not None

    def _run(self, cmd: list[str]) -> tuple[bool, str]:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            return (res.returncode == 0, res.stdout.strip())
        except Exception as e:
            return (False, str(e))

    # --- Media Playback Controls ---

    def play_pause(self) -> bool:
        """Toggle playback across active media sources (YouTube, Spotify, MPRIS)."""
        if self.has_omarchy_shell:
            ok, out = self._run(["omarchy-shell", "media", "playPause"])
            if ok and "ok" in out.lower():
                return True

        if self.has_playerctl:
            ok, _ = self._run(["playerctl", "play-pause"])
            return ok
        return False

    def pause(self) -> bool:
        """Pause playback."""
        # omarchy-shell media playPause acts as toggle; if playerctl is present, try specific pause first
        if self.has_playerctl:
            ok, _ = self._run(["playerctl", "pause"])
            if ok:
                return True
        # If playerctl couldn't pause or player isn't classic MPRIS, invoke omarchy-shell
        return self.play_pause()

    def play(self) -> bool:
        """Resume playback."""
        if self.has_playerctl:
            ok, _ = self._run(["playerctl", "play"])
            if ok:
                return True
        return self.play_pause()

    def next_track(self) -> bool:
        """Skip to the next media track."""
        if self.has_omarchy_shell:
            ok, out = self._run(["omarchy-shell", "media", "next"])
            if ok and "ok" in out.lower():
                return True

        if self.has_playerctl:
            ok, _ = self._run(["playerctl", "next"])
            return ok
        return False

    def previous_track(self) -> bool:
        """Return to previous media track."""
        if self.has_omarchy_shell:
            ok, out = self._run(["omarchy-shell", "media", "previous"])
            if ok and "ok" in out.lower():
                return True

        if self.has_playerctl:
            ok, _ = self._run(["playerctl", "previous"])
            return ok
        return False

    def get_track_info(self) -> Dict[str, str]:
        """Return current metadata (title, artist, status)."""
        if self.has_playerctl:
            _, status = self._run(["playerctl", "status"])
            _, title = self._run(["playerctl", "metadata", "title"])
            _, artist = self._run(["playerctl", "metadata", "artist"])
            return {
                "status": status.lower(),
                "title": title,
                "artist": artist,
            }
        return {"status": "unknown", "title": "", "artist": ""}

    # --- PipeWire Audio Controls (omarchy scripts / wpctl) ---

    def volume_up(self, step_percent: int = 5) -> bool:
        """Increase default audio sink volume."""
        if self.has_omarchy_vol and step_percent == 5:
            ok, _ = self._run(["omarchy-audio-output-volume", "raise"])
            if ok:
                return True
        if self.has_wpctl:
            ok, _ = self._run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{step_percent}%+"]
            )
            return ok
        return False

    def volume_down(self, step_percent: int = 5) -> bool:
        """Decrease default audio sink volume."""
        if self.has_omarchy_vol and step_percent == 5:
            ok, _ = self._run(["omarchy-audio-output-volume", "lower"])
            if ok:
                return True
        if self.has_wpctl:
            ok, _ = self._run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{step_percent}%-"]
            )
            return ok
        return False

    def set_volume(self, percent: int) -> bool:
        """Set absolute volume level (0-100)."""
        if self.has_wpctl:
            ratio = max(0.0, min(1.5, percent / 100.0))
            ok, _ = self._run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{ratio:.2f}"])
            return ok
        return False

    def toggle_mute_output(self) -> bool:
        """Toggle audio output mute."""
        if self.has_omarchy_vol:
            ok, _ = self._run(["omarchy-audio-output-volume", "mute-toggle"])
            if ok:
                return True
        if self.has_wpctl:
            ok, _ = self._run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
            return ok
        return False

    def set_mic_mute(self, muted: bool = True) -> bool:
        """Mute or unmute default audio capture source (microphone)."""
        if self.has_wpctl:
            val = "1" if muted else "0"
            ok, _ = self._run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", val])
            return ok
        if self.has_omarchy_mic:
            ok, _ = self._run(["omarchy-audio-input-mute"])
            return ok
        return False

    def toggle_mic_mute(self) -> bool:
        """Toggle microphone mute."""
        if self.has_omarchy_mic:
            ok, _ = self._run(["omarchy-audio-input-mute"])
            if ok:
                return True
        if self.has_wpctl:
            ok, _ = self._run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"])
            return ok
        return False
