"""Jarvis Core Background IPC Daemon for Omarchy Linux."""

import json
import os
import signal
import socket
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from core.dispatcher import CommandDispatcher
from core.system2_agent import System2Agent
from core.tts_kokoro import AVAILABLE_VOICES, KokoroTTS
from core.voxtype_bridge import VoxtypeBridge


class JarvisDaemon:
    """Central background server for voice automation, IPC coordination, and execution."""

    def __init__(self, socket_path: Optional[str] = None):
        self.runtime_dir = os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"
        )
        self.jarvis_dir = os.path.join(self.runtime_dir, "jarvis")
        os.makedirs(self.jarvis_dir, exist_ok=True)

        self.socket_path = socket_path or os.path.join(
            self.jarvis_dir, "ipc.sock"
        )
        self.tts = KokoroTTS(lazy_init=True)
        self.system2 = System2Agent(tts=self.tts, enable_tts=True)
        self.dispatcher = CommandDispatcher(system2=self.system2)
        self.voxtype = VoxtypeBridge()

        self.state = "idle"
        self.last_command = ""
        self.last_result: Dict[str, Any] = {}
        self.running = False
        self._server_sock: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._lock = threading.Lock()

    def set_state(self, new_state: str):
        """Update system state and notify subscribers."""
        with self._lock:
            if self.state != new_state:
                self.state = new_state
                self._broadcast({"type": "state_change", "state": self.state})

    def _broadcast(self, msg: dict):
        """Broadcast an event message to all connected clients."""
        payload = (json.dumps(msg) + "\n").encode("utf-8")
        dead_clients = []
        for client in self._clients:
            try:
                client.sendall(payload)
            except Exception:
                dead_clients.append(client)
        for dead in dead_clients:
            if dead in self._clients:
                self._clients.remove(dead)

    def handle_request(self, req: dict) -> dict:
        """Handle incoming IPC JSON request."""
        action = req.get("action", "")

        if action == "get_status":
            return {
                "status": "ok",
                "state": self.state,
                "last_command": self.last_command,
                "last_result": self.last_result,
            }

        elif action == "execute_text":
            text = req.get("text", "").strip()
            if not text:
                return {"status": "error", "error": "Empty text provided"}

            self.set_state("executing")
            res = self.dispatcher.dispatch_text(text)
            self.last_command = text
            self.last_result = res
            self.set_state("idle")
            return {"status": "ok", "result": res}

        elif action == "classify":
            text = req.get("text", "").strip()
            if not text:
                return {"status": "error", "error": "Empty text provided"}
            res = self.dispatcher.laya.predict(text)
            return {"status": "ok", "result": res}

        elif action == "agent_prompt":
            text = req.get("text", "").strip()
            speak = req.get("speak", True)
            if not text:
                return {"status": "error", "error": "Empty prompt provided"}
            self.set_state("deliberating")
            res = self.system2.query(text, speak=speak)
            self.set_state("idle")
            return {"status": "ok", "result": res}

        elif action == "speak":
            text = req.get("text", "").strip()
            voice = req.get("voice")
            speed = float(req.get("speed", 1.0))
            block = req.get("block", False)
            if not text:
                return {"status": "error", "error": "Empty text provided"}
            res = self.tts.speak(text, voice=voice, speed=speed, block=block)
            return {"status": "ok", "result": res}

        elif action == "list_voices":
            return {"status": "ok", "result": self.tts.list_voices()}

        elif action == "set_voice":
            voice = req.get("voice", "").strip()
            if voice in AVAILABLE_VOICES:
                self.tts.default_voice = voice
                return {"status": "ok", "default_voice": voice}
            return {
                "status": "error",
                "error": f"Unknown voice: {voice}. Choose from: {list(AVAILABLE_VOICES.keys())}",
            }

        elif action == "record_start":
            ok = self.voxtype.start_recording()
            if ok:
                self.set_state("recording")
                return {"status": "ok", "state": "recording"}
            return {"status": "error", "error": "Failed to start Voxtype recording"}

        elif action == "record_stop":
            return self._stop_and_dispatch()

        elif action == "record_toggle":
            if self.state == "recording" or self.voxtype.is_recording():
                return self._stop_and_dispatch()
            else:
                ok = self.voxtype.start_recording()
                if ok:
                    self.set_state("recording")
                    return {"status": "ok", "state": "recording"}
                return {"status": "error", "error": "Failed to start Voxtype recording"}

        return {"status": "error", "error": f"Unknown action: {action}"}

    def _stop_and_dispatch(self) -> dict:
        """Stop recording, await transcription, and dispatch matching command."""
        self.set_state("transcribing")
        self.voxtype.stop_recording()

        # Await transcribed speech from Voxtype
        text = self.voxtype.wait_for_transcription(timeout_sec=6.0)

        if not text:
            self.set_state("idle")
            return {
                "status": "warning",
                "state": "idle",
                "message": "No speech detected or transcription timed out",
            }

        self.set_state("executing")
        self.last_command = text
        res = self.dispatcher.dispatch_text(text)
        self.last_result = res

        # If System 2 requires clarification, transition to clarifying and rearm Voxtype
        if res.get("requires_clarification"):
            self.set_state("clarifying")
            self.voxtype.start_recording()
            return {
                "status": "ok",
                "state": "clarifying",
                "transcription": text,
                "result": res,
                "clarification_prompt": res.get("response"),
            }

        self.set_state("idle")
        return {
            "status": "ok",
            "state": "idle",
            "transcription": text,
            "result": res,
        }

    def _client_handler(self, client_sock: socket.socket):
        """Worker thread per connected IPC client."""
        client_sock.settimeout(None)
        with self._lock:
            self._clients.append(client_sock)

        buffer = ""
        try:
            while self.running:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                        resp = self.handle_request(req)
                    except json.JSONDecodeError:
                        resp = {"status": "error", "error": "Invalid JSON format"}
                    client_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception:
            pass
        finally:
            with self._lock:
                if client_sock in self._clients:
                    self._clients.remove(client_sock)
            try:
                client_sock.close()
            except Exception:
                pass

    def start(self):
        """Bind Unix socket and run IPC event loop."""
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.socket_path)
        os.chmod(self.socket_path, 0o700)
        self._server_sock.listen(10)
        self.running = True
        self.set_state("idle")

        def shutdown_handler(signum, frame):
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

        while self.running:
            try:
                client, _ = self._server_sock.accept()
                t = threading.Thread(
                    target=self._client_handler, args=(client,), daemon=True
                )
                t.start()
            except Exception:
                if not self.running:
                    break

    def stop(self):
        """Stop daemon and cleanup resources."""
        self.running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass


def main():
    daemon = JarvisDaemon()
    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
