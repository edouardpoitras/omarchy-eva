"""Configuration management for Eva desktop automation suite.

Manages persistent configuration in ~/.config/eva/config.json with support
for runtime retrieval, dynamic updates, and verbosity filtering.
"""

import json
import os
import threading
from typing import Any, Dict, Optional

CONFIG_DIR = os.path.expanduser("~/.config/eva")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "name": "Eva",
    "voice": "bf_emma",         # Default female neural voice (British)
    "voice_speed": 1.0,
    "verbosity": "minimal",      # "minimal" (speak queries/errors only), "verbose" (speak everything), "silent" (no speech)
    "sound_effects": True,       # Enable/disable earcon chimes
    "earcon_volume": 0.25,       # Gentle, subtle earcon volume (0.0 to 1.0)
    "hud_enabled": True,         # Show floating visual overlay on listening/executing
    "tray_enabled": True,        # Enable system tray StatusNotifierItem
    "default_agent": "gemini",   # Deliberative System 2 agent CLI
}

# Intents whose actions are immediately visual/tactile and should not produce spoken confirmations in minimal mode
VISUAL_SILENT_INTENTS = {
    "HYPR_WORKSPACE",
    "HYPR_WINDOW_MOVE",
    "HYPR_WINDOW",
    "HYPR_FOCUS",
    "APP_LAUNCH",
    "APP_CLOSE",
    "VISUAL_CLICK",
    "AUDIO_VOLUME",             # volume up/down/mute (user sees OSD / hears volume change)
    "AUDIO_CONTROL",
    "DEVICE_BRIGHTNESS",        # brightness changes
    "DEVICE_CONTROL",
    "DEVICE_DND",
    "DEVICE_BAR",
}

VISUAL_SILENT_ACTIONS = {
    "workspace",
    "movetoworkspace",
    "close_window",
    "close",
    "toggle_fullscreen",
    "toggle_floating",
    "toggle_split",
    "toggle_pseudo",
    "toggle_scratchpad",
    "focus_direction",
    "swap_window",
    "move_window",
    "launch",
    "open",
    "volume_up",
    "volume_down",
    "set_volume",
    "mute_toggle",
    "set_brightness",
    "brightness_up",
    "brightness_down",
    "dim_screen",
    "toggle_dnd",
    "toggle_top_bar",
    "toggle_nightlight",
    "lock_session",
}


class EvaConfig:
    """Thread-safe persistent configuration manager for Eva."""

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = config_path
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self):
        """Load configuration from disk, creating defaults if not present."""
        with self._lock:
            if not os.path.exists(self.config_path):
                self._data = dict(DEFAULT_CONFIG)
                self._save_unlocked()
                return

            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge with defaults to ensure all keys exist
                merged = dict(DEFAULT_CONFIG)
                merged.update(data)
                self._data = merged
            except Exception:
                self._data = dict(DEFAULT_CONFIG)

    def _save_unlocked(self):
        """Internal save without acquiring lock (must be called inside with self._lock)."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    def save(self):
        """Persist current configuration to disk."""
        with self._lock:
            self._save_unlocked()

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        with self._lock:
            return self._data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any):
        """Set configuration value and persist immediately."""
        with self._lock:
            self._data[key] = value
            self._save_unlocked()

    def as_dict(self) -> Dict[str, Any]:
        """Return a copy of the configuration dictionary."""
        with self._lock:
            return dict(self._data)

    def reset(self):
        """Reset configuration to defaults."""
        with self._lock:
            self._data = dict(DEFAULT_CONFIG)
            self._save_unlocked()

    @property
    def verbosity(self) -> str:
        return str(self.get("verbosity", "minimal")).lower()

    @property
    def voice(self) -> str:
        return str(self.get("voice", "bf_emma"))

    @property
    def earcon_volume(self) -> float:
        try:
            return float(self.get("earcon_volume", 0.25))
        except (ValueError, TypeError):
            return 0.25

    def should_speak_action(
        self,
        intent: Optional[str] = None,
        action: Optional[str] = None,
        is_query: bool = False,
        is_error: bool = False,
    ) -> bool:
        """Determine whether an executed action should produce spoken voice feedback.

        Rules:
        - "silent": Only speak on critical errors or explicit agent queries.
        - "minimal" (default): Speak on queries, errors, and informational requests. Suppress
          speech for visual actions like moving windows, launching apps, or changing volume.
        - "verbose": Speak on every action confirmation.
        """
        verb = self.verbosity

        if verb == "silent":
            return is_error

        if verb == "verbose":
            return True

        # Minimal mode (default):
        # Auto-detect query from action or intent if not explicitly flagged
        if action and any(q_word in action.lower() for q_word in ("list", "status", "query", "get", "where", "what", "which", "identify", "overview")):
            is_query = True

        # Always speak on errors or questions/queries
        if is_error or is_query:
            return True

        # Check intent classification
        if intent and intent in VISUAL_SILENT_INTENTS:
            return False

        # Check action prefix or keyword
        if action:
            act_clean = action.lower()
            for silent_act in VISUAL_SILENT_ACTIONS:
                if act_clean.startswith(silent_act) or silent_act in act_clean:
                    return False

        # Informational intents always speak
        if intent in (
            "EVA_IDENTITY",
            "EVA_CAPABILITIES",
            "MEDIA_QUERY",
            "SYSTEM_TELEMETRY",
            "ESCALATE_GENERATIVE",
            "AWARENESS_ALERT",
        ):
            return True

        return True


# Global singleton
eva_config = EvaConfig()
