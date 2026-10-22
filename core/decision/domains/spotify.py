"""Specialized Spotify System 1 Decision Model."""

import subprocess
import time
import urllib.parse
from typing import Any, Dict, Optional

from core.app_indexer import AppIndexer
from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor


class SpotifyDomainModel:
    """Specialized System 1 model for Spotify actions and controls."""

    def __init__(self, engine: BaseDecisionEngine, apps: Optional[AppIndexer] = None):
        self.engine = engine
        self.apps = apps or AppIndexer()

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef decision question schema for Spotify."""
        return {
            "spotify_action": DecisionQuestion(
                question_id="spotify_action",
                question_type="choice",
                instructions="Determine the exact Spotify operation requested by the user.",
                criteria={
                    "play_track_artist": "Play a specific song, track, or artist (e.g., 'play bohemian rhapsody by queen', 'play hotel california')",
                    "search_and_play": "Search for music, album, or playlist on Spotify",
                    "toggle_playback": "Play, pause, or resume Spotify playback",
                    "next_track": "Skip to the next Spotify track",
                    "previous_track": "Go back to the previous Spotify track",
                    "open_spotify": "Launch or focus the Spotify application window",
                },
            )
        }

    def _is_spotify_running(self) -> bool:
        """Check if Spotify MPRIS service is registered on the D-Bus session bus."""
        cmd = [
            "dbus-send",
            "--session",
            "--dest=org.freedesktop.DBus",
            "--type=method_call",
            "--print-reply",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus.ListNames",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=1.0)
            return "org.mpris.MediaPlayer2.spotify" in res.stdout
        except Exception:
            return False

    def _send_dbus(self, method: str, arg: Optional[str] = None) -> bool:
        """Send method call to Spotify via D-Bus MPRIS."""
        cmd = [
            "dbus-send",
            "--session",
            "--dest=org.mpris.MediaPlayer2.spotify",
            "--type=method_call",
            "/org/mpris/MediaPlayer2",
            f"org.mpris.MediaPlayer2.Player.{method}",
        ]
        if arg is not None:
            cmd.append(f"string:{arg}")
        try:
            res = subprocess.run(cmd, capture_output=True, check=False, timeout=1.5)
            return res.returncode == 0
        except Exception:
            return False

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the Spotify action."""
        schema = self.get_question_schema()
        decisions = self.engine.predict(state=text, questions=schema, context=context)
        action_res = decisions.get("spotify_action")
        action = action_res.selected_option if action_res else "search_and_play"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_spotify_tokens(text)

        if dry_run:
            return {
                "domain": "spotify",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action in ("play_track_artist", "search_and_play"):
            query = tokens.get("query") or tokens.get("track") or tokens.get("artist") or text
            track = tokens.get("track")
            artist = tokens.get("artist")

            # 1. Ensure Spotify is running
            if not self._is_spotify_running():
                entry = self.apps.find_app("spotify")
                if entry:
                    self.apps.launch("spotify")
                else:
                    try:
                        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    except Exception:
                        pass
                # Wait for Spotify D-Bus service to appear
                for _ in range(15):
                    time.sleep(0.2)
                    if self._is_spotify_running():
                        break

            # 2. Instruct Spotify via D-Bus OpenUri to search and start playback
            uri = f"spotify:search:{query}"
            ok = self._send_dbus("OpenUri", uri)
            if ok:
                success = True
                # Ensure playback starts
                time.sleep(0.3)
                self._send_dbus("Play")
            else:
                # Fallback to xdg-open URI scheme handler
                encoded = urllib.parse.quote(query)
                try:
                    subprocess.Popen(
                        ["xdg-open", f"spotify:search:{encoded}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    success = True
                except Exception:
                    success = False

            if track and artist:
                speech = f"Playing {track} by {artist} on Spotify."
            elif track:
                speech = f"Playing {track} on Spotify."
            else:
                speech = f"Playing {query} on Spotify."

        elif action == "toggle_playback":
            success = self._send_dbus("PlayPause")
            speech = "Toggled Spotify playback."

        elif action == "next_track":
            success = self._send_dbus("Next")
            speech = "Skipped to next Spotify track."

        elif action == "previous_track":
            success = self._send_dbus("Previous")
            speech = "Previous Spotify track."

        elif action == "open_spotify":
            entry = self.apps.find_app("spotify")
            if entry:
                success = self.apps.launch("spotify")
                speech = "Opening Spotify."
            else:
                success = False

        return {
            "domain": "spotify",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
