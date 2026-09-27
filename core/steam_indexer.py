"""Steam Game Discovery, Indexing, and Launch Manager for Omarchy Linux."""

import os
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional


class SteamIndexer:
    """Discovers installed Steam games across all libraries and handles game execution."""

    DEFAULT_STEAM_ROOTS = [
        os.path.expanduser("~/.local/share/Steam"),
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.steam/root"),
        os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam"),
        os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.steam/steam"),
    ]

    NON_GAME_PREFIXES = (
        "proton",
        "steam linux runtime",
        "steamworks common redistributables",
        "steam controller configs",
    )

    def __init__(self, steam_roots: Optional[List[str]] = None):
        self.steam_roots = steam_roots or self.DEFAULT_STEAM_ROOTS
        self._games: Dict[str, Dict[str, Any]] = {}
        self._libraries: List[str] = []
        self.refresh()

    @staticmethod
    def _normalize(text: str) -> str:
        """Strip non-alphanumeric characters and lowercase for robust fuzzy matching."""
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def _discover_libraries(self) -> List[str]:
        """Find all Steam library folders by checking default roots and parsing libraryfolders.vdf."""
        libraries = set()

        for root in self.steam_roots:
            if not os.path.isdir(root):
                continue
            libraries.add(root)

            # Check libraryfolders.vdf in this root's steamapps/
            vdf_path = os.path.join(root, "steamapps", "libraryfolders.vdf")
            if os.path.isfile(vdf_path):
                try:
                    with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    # Find all "path" "..." entries
                    for match in re.finditer(r'\"path\"\s+\"([^\"]+)\"', content):
                        lib_path = match.group(1).replace("\\\\", "/")
                        if os.path.isdir(lib_path):
                            libraries.add(lib_path)
                except Exception:
                    pass

        return sorted(list(libraries))

    def _parse_acf(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse a Steam appmanifest_<appid>.acf file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return None

        def extract_field(field_name: str, default: str = "") -> str:
            m = re.search(rf'\"{re.escape(field_name)}\"\s+\"([^\"]*)\"', content)
            return m.group(1) if m else default

        appid = extract_field("appid")
        name = extract_field("name")
        installdir = extract_field("installdir")
        state_flags = extract_field("StateFlags", "0")
        size_on_disk = extract_field("SizeOnDisk", "0")
        last_played = extract_field("LastPlayed", "0")

        if not appid or not name:
            return None

        # Check if it's a runtime tool or actual game
        name_lower = name.lower()
        is_tool = any(name_lower.startswith(p) for p in self.NON_GAME_PREFIXES)

        return {
            "appid": appid,
            "name": name,
            "installdir": installdir,
            "state_flags": state_flags,
            "size_on_disk": int(size_on_disk) if size_on_disk.isdigit() else 0,
            "last_played": int(last_played) if last_played.isdigit() else 0,
            "is_game": not is_tool,
            "manifest_path": file_path,
            "exec": f"steam steam://rungameid/{appid}",
        }

    def refresh(self):
        """Scan all discovered Steam library folders and re-index installed games."""
        self._libraries = self._discover_libraries()
        games: Dict[str, Dict[str, Any]] = {}

        for lib in self._libraries:
            steamapps = os.path.join(lib, "steamapps")
            if not os.path.isdir(steamapps):
                continue

            for fname in os.listdir(steamapps):
                if fname.startswith("appmanifest_") and fname.endswith(".acf"):
                    acf_path = os.path.join(steamapps, fname)
                    entry = self._parse_acf(acf_path)
                    if entry and entry.get("appid"):
                        games[entry["appid"]] = entry

        self._games = games

    def list_games(self, include_tools: bool = False) -> List[Dict[str, Any]]:
        """Return list of indexed games sorted by name."""
        res = [
            g for g in self._games.values()
            if include_tools or g.get("is_game", True)
        ]
        return sorted(res, key=lambda x: x["name"].lower())

    def find_game(self, query: str) -> Optional[Dict[str, Any]]:
        """Look up game by appid, name, installdir, or normalized fuzzy match."""
        q = query.strip()
        if not q:
            return None

        q_lower = q.lower()
        q_norm = self._normalize(q)

        # 1. Direct App ID match
        if q in self._games:
            return self._games[q]

        # 2. Exact name match (case-insensitive)
        for g in self._games.values():
            if g["name"].lower() == q_lower:
                return g

        # 3. Exact installdir match (case-insensitive)
        for g in self._games.values():
            if g.get("installdir", "").lower() == q_lower:
                return g

        # 4. Normalized alphanumeric match (handles "rocketleague" -> "Rocket League")
        if q_norm:
            # First check games
            for g in self._games.values():
                if g.get("is_game", True):
                    if self._normalize(g["name"]) == q_norm or self._normalize(g.get("installdir", "")) == q_norm:
                        return g

            # Substring normalized match
            for g in self._games.values():
                if g.get("is_game", True):
                    g_norm = self._normalize(g["name"])
                    if q_norm in g_norm or g_norm in q_norm:
                        return g

            # Include tools if no game matched
            for g in self._games.values():
                if not g.get("is_game", True):
                    if self._normalize(g["name"]) == q_norm or q_norm in self._normalize(g["name"]):
                        return g

        return None

    def launch_game(self, query: str) -> Dict[str, Any]:
        """Find and launch the Steam game matching query via steam://rungameid/."""
        game = self.find_game(query)
        if not game:
            return {
                "success": False,
                "error": f"Game '{query}' not found in Steam libraries.",
            }

        appid = game["appid"]
        cmd_str = f"steam steam://rungameid/{appid}"

        try:
            hypr_sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
            if hypr_sig:
                subprocess.Popen(
                    ["hyprctl", "dispatch", "exec", cmd_str],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            else:
                subprocess.Popen(
                    shlex.split(cmd_str),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            return {
                "success": True,
                "appid": appid,
                "name": game["name"],
                "exec": cmd_str,
            }
        except Exception as e:
            return {
                "success": False,
                "appid": appid,
                "name": game["name"],
                "error": str(e),
            }
