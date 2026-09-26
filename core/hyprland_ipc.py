"""Hyprland IPC client providing sub-millisecond control over the Omarchy compositor."""

import json
import os
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple


class HyprlandIPC:
    """Direct Unix domain socket client for Hyprland compositor control in Omarchy."""

    def __init__(self, signature: Optional[str] = None):
        self.runtime_dir = os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"
        )
        self.signature = signature or self._discover_signature()
        self.socket_path = (
            os.path.join(self.runtime_dir, "hypr", self.signature, ".socket.sock")
            if self.signature
            else ""
        )
        self.event_socket_path = (
            os.path.join(self.runtime_dir, "hypr", self.signature, ".socket2.sock")
            if self.signature
            else ""
        )

    def _discover_signature(self) -> str:
        """Discover active Hyprland instance signature from environment or runtime dir."""
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        if sig:
            return sig

        hypr_base = os.path.join(self.runtime_dir, "hypr")
        if os.path.isdir(hypr_base):
            for entry in os.listdir(hypr_base):
                candidate = os.path.join(hypr_base, entry, ".socket.sock")
                if os.path.exists(candidate):
                    return entry
        return ""

    def is_available(self) -> bool:
        """Check if Hyprland's control socket is accessible."""
        if not self.signature or not self.socket_path:
            self.signature = self._discover_signature()
            if self.signature:
                self.socket_path = os.path.join(
                    self.runtime_dir, "hypr", self.signature, ".socket.sock"
                )
        return bool(self.socket_path and os.path.exists(self.socket_path))

    def send_raw(self, command: str) -> str:
        """Send a raw command string to Hyprland's control socket.

        In Omarchy, dispatch commands use Hyprland Lua syntax, e.g.:
          - 'dispatch hl.dsp.focus({ workspace = "3" })'
          - 'j/activewindow' (JSON)
          - 'j/clients' (JSON)
        """
        if not self.is_available():
            try:
                res = subprocess.run(
                    ["hyprctl", "dispatch", command],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                return res.stdout
            except Exception as e:
                return f"ERR: {e}"

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1.0)
                sock.connect(self.socket_path)
                sock.sendall(command.encode("utf-8"))

                chunks = []
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    chunks.append(data)
                return b"".join(chunks).decode("utf-8", errors="replace")
        except Exception as e:
            try:
                res = subprocess.run(
                    ["hyprctl", "dispatch", command],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                return res.stdout
            except Exception:
                return f"ERR: {e}"

    def dispatch_lua(self, lua_call: str) -> bool:
        """Execute a Hyprland Lua dispatcher call directly (e.g. 'hl.dsp.focus(...)')."""
        payload = f"dispatch {lua_call}"
        resp = self.send_raw(payload).strip()
        return "ok" in resp.lower()

    def focus_workspace(self, ws: str) -> bool:
        """Switch to workspace (e.g. '1', '2', 'e+1', 'e-1')."""
        return self.dispatch_lua(f"hl.dsp.focus({{ workspace = '{ws}' }})")

    def move_window_to_workspace(self, ws: str) -> bool:
        """Move active window to workspace."""
        return self.dispatch_lua(f"hl.dsp.window.move({{ workspace = '{ws}' }})")

    def close_window(self) -> bool:
        """Close active window."""
        return self.dispatch_lua("hl.dsp.window.close()")

    def toggle_floating(self) -> bool:
        """Toggle floating state of active window."""
        return self.dispatch_lua("hl.dsp.window.float({ action = 'toggle' })")

    def toggle_fullscreen(self) -> bool:
        """Toggle fullscreen mode of active window."""
        return self.dispatch_lua("hl.dsp.window.fullscreen({ mode = 'fullscreen' })")

    def toggle_split(self) -> bool:
        """Toggle window layout split."""
        return self.dispatch_lua("hl.dsp.layout('togglesplit')")

    def toggle_pseudo(self) -> bool:
        """Toggle pseudo tiled mode for active window."""
        return self.dispatch_lua("hl.dsp.window.pseudo()")

    def toggle_scratchpad(self) -> bool:
        """Toggle scratchpad special workspace."""
        return self.dispatch_lua('hl.dsp.workspace.toggle_special("scratchpad")')

    def move_to_scratchpad(self) -> bool:
        """Move active window to scratchpad silently."""
        return self.dispatch_lua('hl.dsp.window.move({ workspace = "special:scratchpad", follow = false })')

    def focus_direction(self, direction: str) -> bool:
        """Move focus in a direction: 'l'/'left', 'r'/'right', 'u'/'up', 'd'/'down'."""
        d = direction.lower().strip()
        dir_map = {"left": "l", "right": "r", "up": "u", "down": "d", "l": "l", "r": "r", "u": "u", "d": "d"}
        target_dir = dir_map.get(d, "l")
        return self.dispatch_lua(f'hl.dsp.focus({{ direction = "{target_dir}" }})')

    def swap_window_direction(self, direction: str) -> bool:
        """Swap active window with neighbor in given direction."""
        d = direction.lower().strip()
        dir_map = {"left": "l", "right": "r", "up": "u", "down": "d", "l": "l", "r": "r", "u": "u", "d": "d"}
        target_dir = dir_map.get(d, "l")
        return self.dispatch_lua(f'hl.dsp.window.swap({{ direction = "{target_dir}" }})')

    def move_window_direction(self, direction: str) -> bool:
        """Move active window in given direction."""
        d = direction.lower().strip()
        dir_map = {"left": "l", "right": "r", "up": "u", "down": "d", "l": "l", "r": "r", "u": "u", "d": "d"}
        target_dir = dir_map.get(d, "l")
        return self.dispatch_lua(f'hl.dsp.window.move({{ direction = "{target_dir}" }})')

    def focus_window_address(self, address: str) -> bool:
        """Focus window by unique hex address (e.g. '0x5e6b3bcdcf40')."""
        clean_addr = address.strip()
        return self.dispatch_lua(f'hl.dsp.focus({{ window = "address:{clean_addr}" }})')

    def exec_app(self, command: str) -> bool:
        """Launch an application through Hyprland."""
        return self.dispatch_lua(f"hl.dsp.exec('{command}')")

    def get_json(self, command: str) -> Any:
        """Query Hyprland JSON endpoint (e.g. 'j/activewindow', 'j/clients')."""
        resp = self.send_raw(f"j/{command}")
        try:
            return json.loads(resp)
        except Exception:
            return None

    def get_active_window(self) -> Optional[Dict[str, Any]]:
        """Return metadata for the currently focused window."""
        return self.get_json("activewindow")

    def get_clients(self) -> List[Dict[str, Any]]:
        """Return list of all open window clients across all workspaces."""
        clients = self.get_json("clients")
        return clients if isinstance(clients, list) else []

    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Return list of active workspaces."""
        workspaces = self.get_json("workspaces")
        return workspaces if isinstance(workspaces, list) else []

    def find_open_window(self, query: str, app_indexer: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Find an open window matching an app name, class, title, or alias."""
        clean_q = query.lower().strip()
        # Strip common conversational artifacts
        for prefix in ("the ", "app ", "application ", "window ", "program "):
            if clean_q.startswith(prefix):
                clean_q = clean_q[len(prefix):].strip()
        for suffix in (" window", " app", " application"):
            if clean_q.endswith(suffix):
                clean_q = clean_q[:-len(suffix)].strip()

        if not clean_q:
            return None

        # Generic category aliases
        ALIASES = {
            "terminal": ["ghostty", "foot", "kitty", "alacritty", "wezterm", "terminal"],
            "browser": ["firefox", "chromium", "google-chrome", "brave", "zen", "browser"],
            "editor": ["antigravity", "code", "vscodium", "nvim", "neovim", "helix", "gedit"],
            "code": ["antigravity", "code", "vscodium", "nvim", "neovim"],
            "music": ["spotify", "youtube", "rhythmbox", "music"],
            "chat": ["discord", "slack", "signal", "whatsapp", "telegram"],
        }
        candidate_names = [clean_q]
        if clean_q in ALIASES:
            candidate_names.extend(ALIASES[clean_q])

        # Cross-reference with AppIndexer if provided
        indexed_app_name = ""
        indexed_app_id = ""
        if app_indexer:
            app_match = app_indexer.find_app(clean_q)
            if app_match:
                indexed_app_name = app_match.get("name", "").lower()
                indexed_app_id = app_match.get("id", "").lower()
                if indexed_app_name and indexed_app_name not in candidate_names:
                    candidate_names.append(indexed_app_name)
                if indexed_app_id and indexed_app_id not in candidate_names:
                    candidate_names.append(indexed_app_id)

        clients = self.get_clients()

        # Pass 1: Exact or substring match on client class or initialClass
        for candidate in candidate_names:
            for client in clients:
                c_class = client.get("class", "").lower()
                c_init = client.get("initialClass", "").lower()
                if candidate == c_class or candidate == c_init or candidate in c_class or candidate in c_init:
                    return client

        # Pass 2: Match on window title or initialTitle
        for candidate in candidate_names:
            for client in clients:
                c_title = client.get("title", "").lower()
                c_ititle = client.get("initialTitle", "").lower()
                if candidate in c_title or candidate in c_ititle:
                    return client

        # Pass 3: Match on webapp URLs or exec substrings
        for client in clients:
            c_class = client.get("class", "").lower()
            c_title = client.get("title", "").lower()
            if f"chrome-{clean_q}" in c_class or f"{clean_q}.com" in c_class or f"{clean_q}.com" in c_title:
                return client

        return None

    def focus_window_by_query(self, query: str, app_indexer: Optional[Any] = None) -> bool:
        """Find window by query, switch to its workspace, and focus its window address."""
        client = self.find_open_window(query, app_indexer=app_indexer)
        if not client:
            return False

        ws_info = client.get("workspace", {})
        ws_name = str(ws_info.get("name") or ws_info.get("id") or "1")
        address = client.get("address", "")

        # 1. Switch to workspace if not on special
        if ws_name.startswith("special:"):
            self.toggle_scratchpad()
        else:
            self.focus_workspace(ws_name)

        # 2. Focus window address
        if address:
            return self.focus_window_address(address)
        return True

