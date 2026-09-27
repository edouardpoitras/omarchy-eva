"""Eva Core Background IPC Daemon for Omarchy Linux."""

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from core.awareness_engine import AwarenessEngine
from core.config import eva_config
from core.dispatcher import CommandDispatcher
from core.system2_agent import System2Agent
from core.input_controller import InputController
from core.soundscape import Soundscape
from core.tts_kokoro import AVAILABLE_VOICES, KokoroTTS
from core.vision_capture import VisionCapture
from core.voxtype_bridge import VoxtypeBridge


class EvaDaemon:
    """Central background server for voice automation, IPC coordination, and execution."""

    def __init__(self, socket_path: Optional[str] = None):
        self.runtime_dir = os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"
        )
        self.eva_dir = os.path.join(self.runtime_dir, "eva")
        os.makedirs(self.eva_dir, exist_ok=True)

        self.socket_path = socket_path or os.path.join(
            self.eva_dir, "ipc.sock"
        )
        self.sound = Soundscape()
        self.tts = KokoroTTS(lazy_init=True)
        self.system2 = System2Agent(tts=self.tts, enable_tts=True)
        self.dispatcher = CommandDispatcher(system2=self.system2)
        self.voxtype = VoxtypeBridge()
        self.vision = VisionCapture()
        self.input = InputController()

        self._auto_stop_timer: Optional[threading.Timer] = None
        self._idle_reset_timer: Optional[threading.Timer] = None
        self.awareness = AwarenessEngine(
            alert_callback=self.proactive_alert,
            query_agent_callback=self.system2.query if self.system2 else None,
            enabled=True,
        )

        self.state = "idle"
        self.last_command = ""
        self.last_result: Dict[str, Any] = {}
        self.running = False
        self._server_sock: Optional[socket.socket] = None
        self._clients: List[socket.socket] = []
        self._lock = threading.RLock()
        self.set_state("idle")

    def set_state(
        self,
        new_state: str,
        command: Optional[str] = None,
        action: Optional[str] = None,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        response: Optional[str] = None,
    ):
        """Update system state, persist to state.json, and notify subscribers."""
        with self._lock:
            if new_state in ("idle", "listening", "recording", "transcribing", "deliberating"):
                if self._idle_reset_timer is not None:
                    try:
                        self._idle_reset_timer.cancel()
                    except Exception:
                        pass
                    self._idle_reset_timer = None

            self.state = new_state
            if command is not None:
                self.last_command = command
            if action is not None:
                self.last_result["action"] = action
            if intent is not None:
                self.last_result["intent"] = intent
            if confidence is not None:
                self.last_result["confidence"] = confidence

            state_data = {
                "state": self.state,
                "command": self.last_command,
                "action": self.last_result.get("action", ""),
                "intent": self.last_result.get("intent", ""),
                "confidence": self.last_result.get("confidence", 1.0),
                "response": response or self.last_result.get("response", ""),
                "timestamp": time.time(),
            }

            try:
                state_path_eva = os.path.join(self.eva_dir, "state.json")
                tmp_path = f"{state_path_eva}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(state_data, f)
                os.replace(tmp_path, state_path_eva)
            except Exception:
                pass

            self._broadcast({"type": "state_change", **state_data})

    def _schedule_idle_reset(self, delay_sec: float = 1.8):
        """Schedule an automatic transition back to idle after delay_sec.
        Cancels any existing pending reset timer to avoid race conditions."""
        with self._lock:
            if self._idle_reset_timer is not None:
                try:
                    self._idle_reset_timer.cancel()
                except Exception:
                    pass
                self._idle_reset_timer = None

            def _timer_callback():
                with self._lock:
                    self.set_state("idle")
                    self._idle_reset_timer = None

            self._idle_reset_timer = threading.Timer(delay_sec, _timer_callback)
            self._idle_reset_timer.daemon = True
            self._idle_reset_timer.start()

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

    def proactive_alert(
        self,
        title: str,
        message: str,
        speech: Optional[str] = None,
        alert_type: str = "warning",
        requires_clarification: bool = False,
    ):
        """Broadcast proactive spoken alert, display HUD banner, and trigger desktop notification."""
        spoken_text = speech or message
        self.sound.deliberating()
        self.set_state("alert", command=title, action=message, intent=title.upper())

        # 1. Desktop Notification
        urgency = "critical" if alert_type == "critical" else "normal"
        try:
            subprocess.Popen(
                ["notify-send", "-u", urgency, "-a", "Eva", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        # 2. Spoken Butler Voice via Kokoro TTS
        from core.context_memory import context_memory
        context_memory.record_statement(spoken_text)
        if self.tts:
            self.tts.speak(spoken_text, block=False)

        # 3. Reset HUD state after message completes
        def _reset_alert():
            with self._lock:
                if self.state == "alert":
                    self.set_state("clarifying" if requires_clarification else "idle")
                self._idle_reset_timer = None

        with self._lock:
            if self._idle_reset_timer is not None:
                try:
                    self._idle_reset_timer.cancel()
                except Exception:
                    pass
            self._idle_reset_timer = threading.Timer(5.5, _reset_alert)
            self._idle_reset_timer.daemon = True
            self._idle_reset_timer.start()

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

            self.set_state("transcribing", command=text)
            res = self.dispatcher.dispatch_text(text)
            self.last_command = text
            self.last_result = res
            intent = res.get("intent", "")
            action_name = res.get("action", "")
            confidence = res.get("confidence", 1.0)
            self.set_state("executing", command=text, action=action_name, intent=intent, confidence=confidence)
            if res.get("success") and intent != "ESCALATE_GENERATIVE":
                self.sound.success()
            elif not res.get("matched"):
                self.sound.error()

            self._schedule_idle_reset(1.8)

            return {"status": "ok", "result": res}

        elif action == "repeat":
            from core.context_memory import context_memory
            stmt = context_memory.get_last_statement()
            speech = stmt if stmt else "I haven't said anything yet."
            if self.tts:
                self.tts.speak(speech, block=False)
            self.set_state("executing", command="repeat that", action="repeat_statement", intent="REPEAT_STATEMENT", response=speech)
            self._schedule_idle_reset(1.8)
            return {"status": "ok", "statement": speech, "speech": speech}

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
            self.set_state("deliberating", command=text, intent="AGENT_DELIBERATE")
            self.sound.deliberating()
            res = self.system2.query(text, speak=speak)
            self.last_command = text
            self.last_result = res
            self.set_state("executing", command=text, action="Spoke response", intent="AGENT_DELIBERATE", response=res.get("response"))

            self._schedule_idle_reset(2.0)

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
                self.tts._default_voice = voice
                eva_config.set("voice", voice)
                return {"status": "ok", "default_voice": voice}
            return {
                "status": "error",
                "error": f"Unknown voice: {voice}. Choose from: {list(AVAILABLE_VOICES.keys())}",
            }

        elif action == "get_config":
            return {"status": "ok", "config": eva_config.as_dict()}

        elif action == "set_config":
            key = req.get("key")
            value = req.get("value")
            if not key:
                return {"status": "error", "error": "Missing config key"}
            eva_config.set(key, value)
            return {"status": "ok", "key": key, "value": value, "config": eva_config.as_dict()}

        elif action == "capture_screen":
            mode = req.get("mode", "fullscreen")
            path, lat = self.vision.capture_screen(mode=mode)
            if path:
                return {"status": "ok", "path": path, "latency_ms": lat}
            return {"status": "error", "error": "Screen capture failed"}

        elif action == "agent_vision":
            text = req.get("text", "Describe what is on my screen").strip()
            mode = req.get("mode", "fullscreen")
            speak = req.get("speak", True)
            self.set_state("deliberating", command=text, intent="VISION_PERCEIVE")
            self.sound.deliberating()
            res = self.system2.query_vision(text, speak=speak, mode=mode)
            self.last_command = text
            self.last_result = res
            self.set_state("executing", command=text, action="Screen analyzed", intent="VISION_PERCEIVE", response=res.get("response"))

            self._schedule_idle_reset(2.0)

            return {"status": "ok", "result": res}

        elif action == "play_sound":
            name = req.get("name", "listening")
            self.sound.play(name)
            return {"status": "ok", "sound": name}

        elif action == "mouse_move":
            x = int(req.get("x", 0))
            y = int(req.get("y", 0))
            smooth = req.get("smooth", True)
            duration = float(req.get("duration_ms", 240.0))
            ok = self.input.move_cursor_to(x, y, smooth=smooth, duration_ms=duration)
            return {"status": "ok" if ok else "error", "x": x, "y": y}

        elif action == "mouse_click":
            button = req.get("button", "left")
            double = req.get("double", False)
            x = req.get("x")
            y = req.get("y")
            pos = (int(x), int(y)) if (x is not None and y is not None) else None
            ok = self.input.click(button=button, double=double, target_pos=pos)
            return {"status": "ok" if ok else "error"}

        elif action == "keyboard_type":
            text = req.get("text", "")
            delay_ms = int(req.get("delay_ms", 25))
            ok = self.input.type_text(text, delay_ms=delay_ms)
            return {"status": "ok" if ok else "error"}

        elif action == "locate_and_click":
            target = req.get("target", "").strip()
            button = req.get("button", "left")
            double = req.get("double", False)
            if not target:
                return {"status": "error", "error": "Empty target provided"}
            self.set_state("deliberating", command=f"click {target}", intent="VISUAL_CLICK")
            res = self.dispatcher.visual.locate_and_click(target, button=button, double=double)
            action_desc = f"{'double ' if double else ''}{button} click {target}"
            self.set_state("executing", command=f"click {target}", action=action_desc, intent="VISUAL_CLICK", confidence=1.0)
            if res.get("success"):
                self.sound.success()
            else:
                self.sound.error()

            self._schedule_idle_reset(1.8)
            return {"status": "ok", "result": res}

        elif action == "top_processes":
            by = req.get("by", "cpu")
            count = int(req.get("count", 3))
            res = self.dispatcher.system.get_top_processes(by=by, count=count)
            return {"status": "ok", "result": res}

        elif action == "list_apps":
            apps = self.dispatcher.apps.list_apps()
            return {"status": "ok", "apps": apps}

        elif action == "close_app":
            app_name = req.get("app", "").strip()
            if not app_name:
                return {"status": "error", "error": "No app name specified"}
            res = self.dispatcher.system.close_app(app_name)
            return {"status": "ok", "result": res}

        elif action == "system_control":
            sub = req.get("sub", "")
            if sub in ("shutdown", "reboot", "suspend", "lock", "logout"):
                res = self.dispatcher.system.power_action(sub)
            elif sub == "battery":
                res = self.dispatcher.system.get_battery_status()
            elif sub == "disk":
                res = self.dispatcher.system.get_disk_space()
            elif sub == "ram":
                res = self.dispatcher.system.get_ram_status()
            elif sub == "ip":
                res = self.dispatcher.system.get_local_ip()
            elif sub == "read_clipboard":
                res = self.dispatcher.system.read_clipboard()
            elif sub == "clear_clipboard":
                res = self.dispatcher.system.clear_clipboard()
            elif sub == "time":
                res = self.dispatcher.system.get_time_date()
            else:
                return {"status": "error", "error": f"Unknown system control: {sub}"}
            return {"status": "ok", "result": res}

        elif action == "demo_hud":
            def _run_demo():
                self.sound.listening()
                self.set_state("listening", command="")
                time.sleep(1.2)
                self.set_state("transcribing", command="switch to workspace 2")
                time.sleep(0.8)
                self.sound.success()
                self.set_state("executing", command="switch to workspace 2", action="workspace 2", intent="HYPR_WORKSPACE", confidence=1.0)
                time.sleep(2.2)
                self.set_state("idle")
            threading.Thread(target=_run_demo, daemon=True).start()
            return {"status": "ok", "message": "HUD demo running"}

        elif action == "proactive_alert":
            title = req.get("title", "Eva Alert")
            message = req.get("message", "")
            speech = req.get("speech")
            alert_type = req.get("type", "warning")
            clarification = req.get("requires_clarification", False)
            self.proactive_alert(title, message, speech=speech, alert_type=alert_type, requires_clarification=clarification)
            return {"status": "ok"}

        elif action == "awareness_status":
            if hasattr(self, "awareness") and self.awareness:
                return {"status": "ok", "awareness": self.awareness.get_status()}
            return {"status": "error", "error": "Awareness engine not running"}

        elif action == "record_start":
            if self._auto_stop_timer:
                self._auto_stop_timer.cancel()
                self._auto_stop_timer = None

            ok = self.voxtype.start_recording()
            if ok:
                self.sound.listening()
                self.set_state("listening", command="")

                # Auto-stop after 8 seconds of continuous recording to prevent accidental stuck recordings
                def _safety_stop():
                    if self.state in ("listening", "recording"):
                        self._stop_and_dispatch()

                self._auto_stop_timer = threading.Timer(8.0, _safety_stop)
                self._auto_stop_timer.daemon = True
                self._auto_stop_timer.start()

                return {"status": "ok", "state": "listening"}
            return {"status": "error", "error": "Failed to start Voxtype recording"}

        elif action == "record_stop":
            if self._auto_stop_timer:
                self._auto_stop_timer.cancel()
                self._auto_stop_timer = None
            if self.state not in ("listening", "recording") and not self.voxtype.is_recording():
                return {"status": "ok", "state": self.state, "note": "not_recording"}
            return self._stop_and_dispatch()

        elif action == "record_toggle":
            if self.state in ("listening", "recording") or self.voxtype.is_recording():
                if self._auto_stop_timer:
                    self._auto_stop_timer.cancel()
                    self._auto_stop_timer = None
                return self._stop_and_dispatch()
            else:
                return self.handle_request({"action": "record_start"})

        return {"status": "error", "error": f"Unknown action: {action}"}

    def _stop_and_dispatch(self) -> dict:
        """Stop recording, await transcription, and dispatch matching command."""
        if self._auto_stop_timer:
            self._auto_stop_timer.cancel()
            self._auto_stop_timer = None

        self.set_state("transcribing")
        self.voxtype.stop_recording()

        # Await transcribed speech from Voxtype
        text = self.voxtype.wait_for_transcription(timeout_sec=6.0)

        if not text:
            self.sound.error()
            self.set_state("error", command="No speech detected")
            self._schedule_idle_reset(1.2)
            return {
                "status": "warning",
                "state": "idle",
                "message": "No speech detected or transcription timed out",
            }

        self.last_command = text
        res = self.dispatcher.dispatch_text(text)
        self.last_result = res
        intent = res.get("intent", "")
        action_name = res.get("action", "")
        confidence = res.get("confidence", 1.0)

        self.set_state("executing", command=text, action=action_name, intent=intent, confidence=confidence)

        # Play affirmative sound cue for reflex completion
        if res.get("success") and res.get("intent") != "ESCALATE_GENERATIVE":
            self.sound.success()
        elif not res.get("matched"):
            self.sound.error()

        # If System 2 requires clarification, transition to clarifying and rearm Voxtype
        if res.get("requires_clarification"):
            self.set_state("clarifying", command=text, response=res.get("response"))
            self.voxtype.start_recording()
            return {
                "status": "ok",
                "state": "clarifying",
                "transcription": text,
                "result": res,
                "clarification_prompt": res.get("response"),
            }

        self._schedule_idle_reset(1.8)
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
            # Check if another daemon is already serving this socket
            try:
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.settimeout(0.5)
                test_sock.connect(self.socket_path)
                test_sock.close()
                print("Eva daemon is already running on socket. Exiting duplicate process.")
                return
            except (ConnectionRefusedError, OSError):
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
        self.awareness.start()

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
        if self._auto_stop_timer:
            try:
                self._auto_stop_timer.cancel()
            except Exception:
                pass
            self._auto_stop_timer = None
        if self._idle_reset_timer:
            try:
                self._idle_reset_timer.cancel()
            except Exception:
                pass
            self._idle_reset_timer = None
        self.awareness.stop()
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
    daemon = EvaDaemon()
    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
