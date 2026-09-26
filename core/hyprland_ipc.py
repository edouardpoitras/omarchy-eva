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

    def focus_window_by_query(self, query: str) -> bool:
        """Find and focus a window matching an app class or title snippet."""
        q = query.lower().strip()
        clients = self.get_clients()
        # First check class
        for client in clients:
            c_class = client.get("class", "").lower()
            if q == c_class or q in c_class:
                address = client.get("address", "")
                if address:
                    return self.dispatch_lua(f"hl.dsp.focus({{ address = '{address}' }})")

        # Next check window title
        for client in clients:
            title = client.get("title", "").lower()
            if q in title:
                address = client.get("address", "")
                if address:
                    return self.dispatch_lua(f"hl.dsp.focus({{ address = '{address}' }})")

        return False
