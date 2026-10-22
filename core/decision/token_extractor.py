"""Token and Argument Extraction Engine for Eva.

Extracts structured domain parameters (track, artist, workspace, window, URL,
coordinates, CLI commands, etc.) from natural user utterances.
"""

import re
from typing import Any, Dict, Optional


class TokenExtractor:
    """Extracts typed slots and arguments for application-specific commands."""

    @staticmethod
    def extract_spotify_tokens(text: str) -> Dict[str, Any]:
        """Extract track, artist, album, and playlist from Spotify utterances."""
        clean = text.strip()
        tokens: Dict[str, Any] = {
            "track": None,
            "artist": None,
            "album": None,
            "playlist": None,
            "query": None,
        }

        # 1. "play album <album> by <artist>"
        m_album_by = re.search(
            r"\b(?:play|listen\s+to)\s+album\s+[\"']?(.+?)[\"']?\s+by\s+[\"']?(.+?)[\"']?$",
            clean,
            re.IGNORECASE,
        )
        if m_album_by:
            tokens["album"] = m_album_by.group(1).strip()
            tokens["artist"] = m_album_by.group(2).strip()
            tokens["query"] = f"{tokens['album']} {tokens['artist']}"
            return tokens

        # 2. "play playlist <playlist>"
        m_playlist = re.search(
            r"\b(?:play|listen\s+to)\s+playlist\s+[\"']?(.+?)[\"']?(?:\s+on\s+spotify)?$",
            clean,
            re.IGNORECASE,
        )
        if m_playlist:
            tokens["playlist"] = m_playlist.group(1).strip()
            tokens["query"] = tokens["playlist"]
            return tokens

        # 3. "play <track> by <artist>"
        # e.g., "play bohemian rhapsody by queen", "play the song bohemian rhapsody by queen"
        m_by = re.search(
            r"\b(?:play|listen\s+to|queue|put\s+on)(?:\s+the)?(?:\s+song|\s+track)?\s+[\"']?(.+?)[\"']?\s+by\s+[\"']?(.+?)[\"']?(?:\s+on\s+spotify)?$",
            clean,
            re.IGNORECASE,
        )
        if m_by:
            tokens["track"] = m_by.group(1).strip()
            tokens["artist"] = m_by.group(2).strip()
            tokens["query"] = f"{tokens['track']} {tokens['artist']}"
            return tokens

        # 4. "play songs by <artist>" / "play artist <artist>"
        m_artist = re.search(
            r"\b(?:play|listen\s+to)(?:\s+songs\s+by|\s+music\s+by|\s+artist)\s+[\"']?(.+?)[\"']?(?:\s+on\s+spotify)?$",
            clean,
            re.IGNORECASE,
        )
        if m_artist:
            tokens["artist"] = m_artist.group(1).strip()
            tokens["query"] = tokens["artist"]
            return tokens

        # 5. "play song <track>" / "play track <track>"
        m_track = re.search(
            r"\b(?:play|listen\s+to|queue)\s+(?:song|track)\s+[\"']?(.+?)[\"']?(?:\s+on\s+spotify)?$",
            clean,
            re.IGNORECASE,
        )
        if m_track:
            tokens["track"] = m_track.group(1).strip()
            tokens["query"] = tokens["track"]
            return tokens

        # 6. Generic "play <query> on spotify" or "search spotify for <query>"
        m_search = re.search(
            r"\b(?:search\s+spotify\s+for|search\s+for|play)\s+[\"']?(.+?)[\"']?\s+(?:on\s+spotify)\b",
            clean,
            re.IGNORECASE,
        )
        if m_search:
            tokens["query"] = m_search.group(1).strip()
            tokens["track"] = tokens["query"]
            return tokens

        # 7. Fallback "play <something>"
        m_gen_play = re.search(
            r"\b(?:play|listen\s+to)\s+[\"']?(.+?)[\"']?$",
            clean,
            re.IGNORECASE,
        )
        if m_gen_play:
            val = m_gen_play.group(1).strip()
            if val.lower() not in ("music", "song", "media", "spotify", "video", "audio"):
                tokens["query"] = val
                tokens["track"] = val

        return tokens

    @staticmethod
    def extract_workspace_tokens(text: str) -> Dict[str, Any]:
        """Extract workspace targets, directions, and window references."""
        clean = text.strip()
        tokens: Dict[str, Any] = {
            "workspace": None,
            "direction": None,
            "app": None,
            "action": None,
        }

        # Numeric workspace: "workspace 3", "desktop 2"
        m_ws = re.search(r"\b(?:workspace|desktop)\s*(\d+|next|prev|previous|another)\b", clean, re.IGNORECASE)
        if m_ws:
            tokens["workspace"] = m_ws.group(1).strip()

        # Directional focus: "focus left", "move up"
        m_dir = re.search(r"\b(?:focus|move|go)\s+(left|right|up|down)\b", clean, re.IGNORECASE)
        if m_dir:
            tokens["direction"] = m_dir.group(1).lower()

        # Window move app target: "move spotify to workspace 4"
        m_app_ws = re.search(
            r"\bmove\s+([a-zA-Z0-9_\-\.\s]+?)\s+to\s+(?:workspace|desktop)\s*(\d+|next|prev|another)\b",
            clean,
            re.IGNORECASE,
        )
        if m_app_ws:
            tokens["app"] = m_app_ws.group(1).strip()
            tokens["workspace"] = m_app_ws.group(2).strip()

        return tokens

    @staticmethod
    def extract_terminal_tokens(text: str) -> Dict[str, Any]:
        """Extract command string or shell intent."""
        clean = text.strip()
        tokens: Dict[str, Any] = {"command": None, "app": "terminal"}

        m_run = re.search(
            r"\b(?:run|execute)\s+[\"']?(.+?)[\"']?(?:\s+in\s+terminal|\s+in\s+bash)?$",
            clean,
            re.IGNORECASE,
        )
        if m_run:
            tokens["command"] = m_run.group(1).strip()

        return tokens

    @staticmethod
    def extract_browser_tokens(text: str) -> Dict[str, Any]:
        """Extract URL or web search query."""
        clean = text.strip()
        tokens: Dict[str, Any] = {"url": None, "query": None}

        # URL extraction
        m_url = re.search(r"\b(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9\-]+\.(?:com|org|net|io|edu|gov|dev))\b", clean, re.IGNORECASE)
        if m_url:
            raw_url = m_url.group(1)
            tokens["url"] = raw_url if raw_url.startswith("http") else f"https://{raw_url}"
            return tokens

        # Search query: "search google for <query>", "search for <query>"
        m_search = re.search(
            r"\b(?:search\s+(?:google|the\s+web|duckduckgo)?\s+for|google)\s+[\"']?(.+?)[\"']?$",
            clean,
            re.IGNORECASE,
        )
        if m_search:
            tokens["query"] = m_search.group(1).strip()

        return tokens

    @staticmethod
    def extract_gui_tokens(text: str) -> Dict[str, Any]:
        """Extract target visual element, coordinates, or type input."""
        clean = text.strip()
        tokens: Dict[str, Any] = {
            "target": None,
            "button": "left",
            "double": False,
            "x": None,
            "y": None,
            "text": None,
        }

        # Coordinates: "click 500 300"
        m_coords = re.search(r"\b(?:click|move)\s+(\d+)\s+(\d+)\b", clean, re.IGNORECASE)
        if m_coords:
            tokens["x"] = int(m_coords.group(1))
            tokens["y"] = int(m_coords.group(2))
            return tokens

        # Double click
        if re.search(r"\bdouble\s+click\b", clean, re.IGNORECASE):
            tokens["double"] = True

        # Right click
        if re.search(r"\bright\s+click\b", clean, re.IGNORECASE):
            tokens["button"] = "right"

        # Type text: "type hello world", "type in 'my search'"
        m_type = re.search(r"\b(?:type|enter)\s+(?:in\s+)?[\"']?(.+?)[\"']?$", clean, re.IGNORECASE)
        if m_type and not any(kw in clean.lower() for kw in ["click", "button"]):
            tokens["text"] = m_type.group(1).strip()
            return tokens

        # Target element: "click on the submit button", "click settings"
        m_target = re.search(
            r"\b(?:click|tap|press)(?:\s+on)?(?:\s+the)?\s+[\"']?(.+?)[\"']?$",
            clean,
            re.IGNORECASE,
        )
        if m_target:
            tokens["target"] = m_target.group(1).strip()

        return tokens

    @staticmethod
    def extract_system_tokens(text: str) -> Dict[str, Any]:
        """Extract volume, brightness, or network parameters."""
        clean = text.strip()
        tokens: Dict[str, Any] = {
            "level": None,
            "delta": None,
            "device": None,
            "network": None,
        }

        # Percentage level
        m_pct = re.search(r"\b(?:set\s+(?:volume|brightness)\s+to|to)\s*(\d+)(?:\s*%)?\b", clean, re.IGNORECASE)
        if m_pct:
            tokens["level"] = int(m_pct.group(1))

        # Wi-Fi network: "connect to wifi Baxter"
        m_wifi = re.search(r"\b(?:connect\s+to\s+wifi|wifi\s+connect)\s+[\"']?(.+?)[\"']?$", clean, re.IGNORECASE)
        if m_wifi:
            tokens["network"] = m_wifi.group(1).strip()

        # Audio device: "switch audio to headset"
        m_dev = re.search(r"\b(?:switch|change)\s+(?:audio|output|mic|microphone)\s+(?:to\s+)?([a-zA-Z0-9_\-]+)\b", clean, re.IGNORECASE)
        if m_dev:
            tokens["device"] = m_dev.group(1).strip()

        return tokens
