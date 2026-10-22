"""Specialized System-Wide Media Playback Decision Model."""

from typing import Any, Dict, Optional

from core.dbus_mpris import DbusMediaControl
from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor


class MediaPlaybackDomainModel:
    """Specialized System 1 model for system-wide media and audio controls."""

    def __init__(self, engine: BaseDecisionEngine, media: Optional[DbusMediaControl] = None):
        self.engine = engine
        self.media = media or DbusMediaControl()

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef decision question schema for system-wide media."""
        return {
            "media_action": DecisionQuestion(
                question_id="media_action",
                question_type="choice",
                instructions="Determine the exact system-wide media or audio action.",
                criteria={
                    "pause": "Pause current media playback (music, video, browser media)",
                    "play": "Resume playback of paused media",
                    "play_pause": "Toggle media playback between playing and paused",
                    "next": "Skip to the next media track",
                    "previous": "Go back to the previous track",
                    "volume_up": "Increase speaker or headphone volume",
                    "volume_down": "Decrease volume",
                    "set_volume": "Set volume to a specific percentage",
                    "mute": "Mute audio output",
                    "unmute": "Unmute audio output",
                    "track_info": "Query the currently playing track title and artist",
                },
            )
        }

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the system media action."""
        schema = self.get_question_schema()
        decisions = self.engine.predict(state=text, questions=schema, context=context)
        action_res = decisions.get("media_action")
        action = action_res.selected_option if action_res else "play_pause"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_system_tokens(text)

        if dry_run:
            return {
                "domain": "media_playback",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action == "pause":
            success = self.media.pause()
            speech = "Paused playback."
        elif action == "play":
            success = self.media.play()
            speech = "Resumed playback."
        elif action == "play_pause":
            success = self.media.play_pause()
            speech = "Toggled playback."
        elif action == "next":
            success = self.media.next_track()
            speech = "Next track."
        elif action == "previous":
            success = self.media.previous_track()
            speech = "Previous track."
        elif action == "volume_up":
            delta = tokens.get("delta") or 5
            success = self.media.volume_up(delta)
            speech = f"Turned volume up {delta} percent."
        elif action == "volume_down":
            delta = tokens.get("delta") or 5
            success = self.media.volume_down(delta)
            speech = f"Turned volume down {delta} percent."
        elif action == "set_volume":
            lvl = tokens.get("level", 50)
            success = self.media.set_volume(lvl)
            speech = f"Set volume to {lvl} percent."
        elif action in ("mute", "unmute"):
            success = self.media.toggle_mute_output()
            speech = "Toggled audio mute."
        elif action == "track_info":
            info = self.media.get_track_info()
            if info.get("title"):
                speech = f"Currently playing {info.get('title')} by {info.get('artist', 'Unknown')}."
                success = True
            else:
                speech = "No media track metadata is currently available."
                success = True

        return {
            "domain": "media_playback",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
