"""Universal Application Indexer and Launcher for Omarchy Linux."""

import os
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional


class AppIndexer:
    """Discovers, indexes, and launches desktop applications installed on the system."""

    DEFAULT_SEARCH_PATHS = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/local/share/applications",
        "/usr/share/applications",
        "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    ]

    GENERIC_CATEGORIES = {
        "browser": ["firefox", "chromium", "google-chrome", "brave", "zen", "omarchy-default-browser"],
        "internet": ["firefox", "chromium", "google-chrome"],
        "terminal": ["ghostty", "foot", "alacritty", "kitty", "omarchy-default-terminal"],
        "shell": ["ghostty", "foot", "alacritty"],
        "console": ["ghostty", "foot", "alacritty"],
        "editor": ["antigravity", "code", "nvim", "neovim", "gedit", "kate", "omarchy-default-editor"],
        "code": ["antigravity", "code", "vscodium"],
        "calculator": ["gnome-calculator", "kcalc", "galculator", "bc"],
        "files": ["nautilus", "thunar", "dolphin", "pcmanfm"],
        "file manager": ["nautilus", "thunar", "dolphin"],
        "music": ["spotify", "cliamp", "rhythmbox", "vlc"],
        "media": ["vlc", "mpv", "spotify"],
        "video": ["vlc", "mpv"],
        "settings": ["omarchy-settings", "gnome-control-center", "systemsettings"],
    }

    def __init__(self, search_paths: Optional[List[str]] = None):
        self.search_paths = search_paths or self.DEFAULT_SEARCH_PATHS
        self._apps: Dict[str, Dict[str, Any]] = {}
        self._alias_map: Dict[str, str] = {}
        self.refresh()

    def refresh(self):
        """Scan application directories and rebuild index."""
        apps: Dict[str, Dict[str, Any]] = {}
        alias_map: Dict[str, str] = {}

        for base_dir in self.search_paths:
            if not os.path.isdir(base_dir):
                continue
            for root, _, files in os.walk(base_dir):
                for f in files:
                    if f.endswith(".desktop"):
                        full_path = os.path.join(root, f)
                        entry = self._parse_desktop_file(full_path)
                        if entry and not entry.get("no_display", False):
                            app_id = entry["id"]
                            # Earlier search paths take precedence (user overrides system)
                            if app_id not in apps:
                                apps[app_id] = entry

        # Build alias map
        for app_id, entry in apps.items():
            name = entry["name"].lower().strip()
            alias_map[name] = app_id
            alias_map[app_id.lower()] = app_id

            # Add binary name from Exec
            exec_bin = entry["clean_exec"].split()[0].lower() if entry.get("clean_exec") else ""
            if exec_bin:
                base_bin = os.path.basename(exec_bin)
                if base_bin not in alias_map:
                    alias_map[base_bin] = app_id

            # Add keywords and generic names
            gen_name = entry.get("generic_name", "").lower().strip()
            if gen_name and gen_name not in alias_map:
                alias_map[gen_name] = app_id

            for kw in entry.get("keywords", []):
                clean_kw = kw.lower().strip()
                if clean_kw and clean_kw not in alias_map:
                    alias_map[clean_kw] = app_id

        # Bind category aliases
        for cat, preferred in self.GENERIC_CATEGORIES.items():
            for p in preferred:
                if p in alias_map:
                    alias_map[cat] = alias_map[p]
                    break

        self._apps = apps
        self._alias_map = alias_map

    def _parse_desktop_file(self, path: str) -> Optional[Dict[str, Any]]:
        """Parse a .desktop entry according to the XDG Desktop Entry Specification."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return None

        # Focus on [Desktop Entry] section
        in_entry = False
        data: Dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line == "[Desktop Entry]":
                in_entry = True
                continue
            elif line.startswith("[") and in_entry:
                break
            if in_entry and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()

        if not data or data.get("Type") != "Application":
            return None

        name = data.get("Name", "")
        exec_str = data.get("Exec", "")
        if not name or not exec_str:
            return None

        # Clean Exec line: remove XDG parameter codes %u, %U, %f, %F, %i, %c, %k
        clean_exec = re.sub(r"%[a-zA-Z]", "", exec_str).strip()

        raw_keywords = data.get("Keywords", "")
        keywords = [k.strip() for k in raw_keywords.split(";") if k.strip()]

        app_id = os.path.splitext(os.path.basename(path))[0]

        return {
            "id": app_id,
            "name": name,
            "path": path,
            "exec": exec_str,
            "clean_exec": clean_exec,
            "generic_name": data.get("GenericName", ""),
            "comment": data.get("Comment", ""),
            "icon": data.get("Icon", ""),
            "terminal": data.get("Terminal", "false").lower() == "true",
            "no_display": data.get("NoDisplay", "false").lower() == "true",
            "keywords": keywords,
        }

    def find_app(self, query: str) -> Optional[Dict[str, Any]]:
        """Look up application by name, alias, keyword, or fuzzy match."""
        q = query.strip().lower()
        if not q:
            return None

        # 1. Exact alias match
        if q in self._alias_map:
            return self._apps[self._alias_map[q]]

        # 2. Name contains query or query contains name
        for app_id, entry in self._apps.items():
            name_lower = entry["name"].lower()
            if q == name_lower or q in name_lower or name_lower in q:
                return entry

        # 3. Base desktop ID match (e.g. 'com.mitchellh.ghostty' matches 'ghostty')
        for app_id, entry in self._apps.items():
            if q in app_id.lower():
                return entry

        # 4. Partial keyword match
        for app_id, entry in self._apps.items():
            for kw in entry.get("keywords", []):
                if q in kw.lower():
                    return entry

        return None

    def launch(self, query: str) -> Dict[str, Any]:
        """Find and launch the application matching query."""
        app = self.find_app(query)
        if not app:
            return {
                "success": False,
                "error": f"Application '{query}' not found on system.",
            }

        cmd_str = app["clean_exec"]
        if app.get("terminal"):
            cmd = ["omarchy-default-terminal", "-e"] + shlex.split(cmd_str)
        else:
            cmd = shlex.split(cmd_str)

        try:
            # First try dispatching via Hyprland IPC if available
            hypr_signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
            if hypr_signature:
                subprocess.Popen(
                    ["hyprctl", "dispatch", "exec", cmd_str],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            else:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return {
                "success": True,
                "app": app["name"],
                "exec": cmd_str,
                "id": app["id"],
            }
        except Exception as e:
            return {
                "success": False,
                "app": app["name"],
                "error": str(e),
            }

    def list_apps(self) -> List[Dict[str, str]]:
        """Return list of indexed applications sorted by name."""
        res = []
        for app_id, entry in sorted(self._apps.items(), key=lambda x: x[1]["name"].lower()):
            res.append({
                "id": app_id,
                "name": entry["name"],
                "generic": entry.get("generic_name", ""),
                "exec": entry.get("clean_exec", ""),
            })
        return res
