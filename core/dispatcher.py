"""Reflex command dispatcher for sub-150ms voice execution on Omarchy."""

import os
import re
import subprocess
import time
from typing import Any, Dict, Optional

from core.app_indexer import AppIndexer
from core.dbus_mpris import DbusMediaControl
from core.hyprland_ipc import HyprlandIPC
from core.system1_laya import LayaDecisionEngine
from core.system2_agent import System2Agent
from core.system_control import SystemControl
from core.visual_grounding import VisualGrounding

# Word to digit mapping for natural speech recognition
NUM_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def normalize_numbers(text: str) -> str:
    """Normalize spoken number words to digits in text."""
    words = text.split()
    normalized = []
    for w in words:
        clean = w.strip(",.?!").lower()
        if clean in NUM_WORDS:
            normalized.append(str(NUM_WORDS[clean]))
        else:
            normalized.append(w)
    return " ".join(normalized)


class CommandDispatcher:
    """High-speed deterministic reflex dispatcher mapping voice transcriptions to OS actions."""

    def __init__(
        self,
        hypr: Optional[HyprlandIPC] = None,
        media: Optional[DbusMediaControl] = None,
        laya: Optional[LayaDecisionEngine] = None,
        system2: Optional[System2Agent] = None,
        apps: Optional[AppIndexer] = None,
        system: Optional[SystemControl] = None,
        visual: Optional[VisualGrounding] = None,
    ):
        self.hypr = hypr or HyprlandIPC()
        self.media = media or DbusMediaControl()
        self.laya = laya or LayaDecisionEngine()
        self.system2 = system2
        self.apps = apps or AppIndexer()
        self.system = system or SystemControl()
        self.visual = visual or VisualGrounding()

    def dispatch_text(self, raw_text: str) -> Dict[str, Any]:
        """Parse raw speech transcription and execute matching reflex command."""
        t_start = time.perf_counter()
        text = raw_text.strip().lower()
        text = normalize_numbers(text)

        # Non-autoregressive Laya decision model inference
        laya_eval = self.laya.predict(raw_text)

        result: Dict[str, Any] = {
            "input": raw_text,
            "normalized": text,
            "matched": False,
            "intent": laya_eval.get("intent", "UNKNOWN") if laya_eval.get("confident") else "UNKNOWN",
            "action": None,
            "success": False,
            "latency_ms": 0.0,
            "laya": laya_eval,
        }

        # 0. Visual UI Element Grounding & Auto-Click
        # e.g., "click on the red button", "click on about", "right click on file", "double click document"
        m_click = re.search(
            r"\b(double\s+click|right\s+click|click|press|tap)\s*(?:on\s+)?(?:the\s+)?(.+)\b",
            raw_text,
            re.IGNORECASE,
        )
        if m_click:
            action_verb = m_click.group(1).lower()
            target_element = m_click.group(2).strip()
            # Avoid collision with media controls, volume or workspace switches
            if (
                target_element not in ("play", "pause", "stop", "next", "previous", "mute", "unmute")
                and not target_element.startswith("workspace")
                and not target_element.startswith("desktop")
            ):
                is_double = "double" in action_verb
                button_type = "right" if "right" in action_verb else "left"
                res = self.visual.locate_and_click(
                    target_element,
                    button=button_type,
                    double=is_double,
                )
                result.update(
                    matched=True,
                    intent="VISUAL_CLICK",
                    action=f"{action_verb} {target_element}",
                    success=res.get("success", False),
                    speech=res.get("speech"),
                    click_result=res,
                )
                if res.get("speech") and self.system2 and self.system2.tts:
                    self.system2.tts.speak(res["speech"], block=False)
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result

        # 1. Move active window to workspace (check first to avoid greedy workspace match)
        # e.g., "move window to workspace 4", "send window to desktop 2"
        m_move = re.search(
            r"\b(?:move|send|transfer)\s*(?:this|window)?\s*(?:to)?\s*(?:workspace|desktop)\s*(\d+)\b",
            text,
        )
        if m_move:
            ws_num = m_move.group(1)
            ok = self.hypr.move_window_to_workspace(ws_num)
            result.update(
                matched=True,
                intent="HYPR_WINDOW_MOVE",
                action=f"movetoworkspace {ws_num}",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # 2. Hyprland: Workspace navigation
        # e.g., "switch to workspace 3", "go to workspace 2", "desktop 4"
        m_ws = re.search(
            r"\b(?:switch to|go to|jump to|open)?\s*(?:workspace|desktop)\s*(\d+)\b",
            text,
        )
        if m_ws:
            ws_num = m_ws.group(1)
            ok = self.hypr.focus_workspace(ws_num)
            result.update(
                matched=True,
                intent="HYPR_WORKSPACE",
                action=f"workspace {ws_num}",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if "next workspace" in text:
            ok = self.hypr.focus_workspace("e+1")
            result.update(
                matched=True,
                intent="HYPR_WORKSPACE",
                action="workspace +1",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if "previous workspace" in text or "prev workspace" in text:
            ok = self.hypr.focus_workspace("e-1")
            result.update(
                matched=True,
                intent="HYPR_WORKSPACE",
                action="workspace -1",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # 3. Hyprland: Window and Application closing
        m_close = re.search(
            r"\b(?:close|quit|kill|exit)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?([a-zA-Z0-9_\-\.\s]+)\b",
            text,
        )
        if m_close:
            target_close = m_close.group(1).strip()
            if target_close in ("window", "this window", "this", "active", "active window", "window now", "current window"):
                ok = self.hypr.close_window()
                result.update(
                    matched=True,
                    intent="HYPR_WINDOW",
                    action="close_window",
                    success=ok,
                )
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result
            elif target_close not in ("session", "workstation", "computer"):
                res = self.system.close_app(target_close)
                result.update(
                    matched=True,
                    intent="APP_CLOSE",
                    action=f"close {target_close}",
                    success=res.get("success", False),
                    speech=res.get("message"),
                )
                if res.get("message") and self.system2 and self.system2.tts:
                    self.system2.tts.speak(res["message"], block=False)
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result

        if "screenshot" not in text and "capture" not in text and any(
            phrase in text
            for phrase in [
                "fullscreen",
                "make fullscreen",
                "toggle fullscreen",
                "full screen",
                "maximize",
            ]
        ):
            ok = self.hypr.toggle_fullscreen()
            result.update(
                matched=True,
                intent="HYPR_WINDOW",
                action="fullscreen",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(
            phrase in text
            for phrase in ["toggle float", "toggle floating", "float window", "make floating"]
        ):
            ok = self.hypr.toggle_floating()
            result.update(
                matched=True,
                intent="HYPR_WINDOW",
                action="togglefloating",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["center window", "center this window", "center active window"]):
            ok = self.system.center_active_window()
            result.update(matched=True, intent="HYPR_WINDOW", action="center_window", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["pin window", "unpin window", "toggle pin"]):
            ok = self.system.pin_active_window()
            result.update(matched=True, intent="HYPR_WINDOW", action="pin_window", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["move window to next monitor", "move window to other monitor", "send window to next monitor"]):
            ok = self.system.move_window_to_monitor("+1")
            result.update(matched=True, intent="HYPR_WINDOW", action="move_to_next_monitor", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Focus specific application window
        # e.g., "focus foot", "focus terminal", "focus chrome", "focus neovim"
        m_focus = re.search(r"\b(?:focus|bring up|switch to)\s+([a-zA-Z0-9_\-]+)\b", text)
        if m_focus and m_focus.group(1) not in ("workspace", "desktop"):
            target_app = m_focus.group(1)
            ok = self.hypr.focus_window_by_query(target_app)
            if ok:
                result.update(
                    matched=True,
                    intent="HYPR_FOCUS",
                    action=f"focus {target_app}",
                    success=True,
                )
                result["latency_ms"] = round(
                    (time.perf_counter() - t_start) * 1000, 2
                )
                return result

        # 4. Media & Audio controls (matches Omarchy keyboard media hotkeys)
        if any(phrase in text for phrase in ["pause music", "pause song", "pause audio", "pause video", "pause playback", "pause"]):
            ok = self.media.pause()
            result.update(
                matched=True,
                intent="MEDIA_CONTROL",
                action="pause",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["play music", "play song", "resume music", "resume video", "resume playback", "play", "unpause"]):
            ok = self.media.play()
            result.update(
                matched=True,
                intent="MEDIA_CONTROL",
                action="play",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["toggle playback", "play pause", "toggle media", "toggle music", "toggle video"]):
            ok = self.media.play_pause()
            result.update(
                matched=True,
                intent="MEDIA_CONTROL",
                action="play_pause",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["next track", "next song", "skip track", "skip song", "skip"]):
            ok = self.media.next_track()
            result.update(
                matched=True,
                intent="MEDIA_CONTROL",
                action="next",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["previous track", "previous song", "prev track"]):
            ok = self.media.previous_track()
            result.update(
                matched=True,
                intent="MEDIA_CONTROL",
                action="previous",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # Volume adjustments
        if any(phrase in text for phrase in ["volume up", "turn it up", "louder", "increase volume"]):
            ok = self.media.volume_up(5)
            result.update(
                matched=True,
                intent="AUDIO_CONTROL",
                action="volume_up 5%",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["volume down", "turn it down", "quieter", "decrease volume", "lower volume"]):
            ok = self.media.volume_down(5)
            result.update(
                matched=True,
                intent="AUDIO_CONTROL",
                action="volume_down 5%",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        m_vol = re.search(r"\b(?:set volume to|volume)\s*(\d+)(?:\s*percent|%)?\b", text)
        if m_vol:
            val = int(m_vol.group(1))
            ok = self.media.set_volume(val)
            result.update(
                matched=True,
                intent="AUDIO_CONTROL",
                action=f"set_volume {val}%",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["unmute mic", "unmute microphone"]):
            ok = self.media.set_mic_mute(False)
            result.update(
                matched=True,
                intent="AUDIO_CONTROL",
                action="mic_mute 0",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["mute mic", "mute microphone", "silence mic"]):
            ok = self.media.set_mic_mute(True)
            result.update(
                matched=True,
                intent="AUDIO_CONTROL",
                action="mic_mute 1",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if text in ["mute", "unmute", "toggle mute"]:
            ok = self.media.toggle_mute_output()
            result.update(
                matched=True,
                intent="AUDIO_CONTROL",
                action="toggle_mute",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # 5. Process Telemetry (Top CPU / Memory without LLM)
        m_top = re.search(
            r"\b(?:top|what(?:'s| is) using(?: the)?(?: most)?)\s*(\d+)?\s*(?:processes|apps|applications)?\s*(?:by|for)?\s*(cpu|processor|memory|ram)\b",
            text,
        )
        count_val = 0
        metric_val = ""
        if m_top:
            count_val = int(m_top.group(1)) if m_top.group(1) else 3
            metric_val = "memory" if m_top.group(2) in ("memory", "ram") else "cpu"
        elif re.search(r"\btop\s+(\d+)\s*(?:processes|apps)?\b", text):
            m_top2 = re.search(r"\btop\s+(\d+)\s*(?:processes|apps)?\b", text)
            count_val = int(m_top2.group(1)) if m_top2 and m_top2.group(1) else 3
            metric_val = "cpu"

        if metric_val:
            res = self.system.get_top_processes(by=metric_val, count=count_val)
            result.update(
                matched=True,
                intent="SYSTEM_TELEMETRY",
                action=f"top_{count_val}_{metric_val}",
                success=res.get("success", False),
                speech=res.get("speech"),
                telemetry_result=res,
            )
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # 6. Power & Session Controls
        if any(phrase in text for phrase in ["shut down", "shutdown", "power off", "turn off the computer", "turn off computer"]):
            res = self.system.power_action("shutdown")
            result.update(matched=True, intent="SYSTEM_POWER", action="shutdown", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["reboot", "restart computer", "restart system", "restart the computer"]):
            res = self.system.power_action("reboot")
            result.update(matched=True, intent="SYSTEM_POWER", action="reboot", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["sleep", "suspend computer", "suspend system", "suspend", "go to sleep"]):
            res = self.system.power_action("suspend")
            result.update(matched=True, intent="SYSTEM_POWER", action="suspend", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["log out", "logout", "exit session"]):
            res = self.system.power_action("logout")
            result.update(matched=True, intent="SYSTEM_POWER", action="logout", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # 7. Hardware Diagnostics & Quick Telemetry
        if any(phrase in text for phrase in ["battery status", "battery level", "battery percentage", "how much battery"]):
            res = self.system.get_battery_status()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="battery_status", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["free disk", "disk space", "how much storage", "how much disk space", "disk storage"]):
            res = self.system.get_disk_space()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="disk_space", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["free memory", "free ram", "how much ram", "memory usage", "available memory"]):
            res = self.system.get_ram_status()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="ram_status", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["what time is it", "current time", "what is the time", "what is the date", "what day is it", "tell me the time"]):
            res = self.system.get_time_date()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="time_date", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["what is my ip", "local ip", "ip address", "my ip address"]):
            res = self.system.get_local_ip()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="local_ip", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["read clipboard", "what is in my clipboard", "what is on my clipboard", "clipboard content", "what's copied"]):
            res = self.system.read_clipboard()
            result.update(matched=True, intent="CLIPBOARD", action="read_clipboard", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["clear clipboard", "empty clipboard"]):
            res = self.system.clear_clipboard()
            result.update(matched=True, intent="CLIPBOARD", action="clear_clipboard", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # 8. System Utilities
        if any(phrase in text for phrase in ["lock screen", "lock workstation", "lock computer", "lock"]):
            ok = self._launch_cmd(["loginctl", "lock-session"])
            result.update(
                matched=True,
                intent="SYSTEM_ACTION",
                action="lock_session",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # Screenshot: fullscreen vs smart region
        if any(phrase in text for phrase in ["fullscreen screenshot", "full screen screenshot", "capture full screen", "screenshot screen"]):
            ok = self._launch_cmd(["omarchy-capture-screenshot", "fullscreen", "slurp"])
            result.update(
                matched=True,
                intent="SYSTEM_ACTION",
                action="fullscreen_screenshot (saved to ~/Pictures & clipboard)",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # Screenshot: defaults to smart slurp (saves to ~/Pictures and copies to clipboard with notification)
        if any(phrase in text for phrase in ["take screenshot", "capture screenshot", "screenshot region", "screenshot"]):
            ok = self._launch_cmd(["omarchy-capture-screenshot", "smart", "slurp"])
            result.update(
                matched=True,
                intent="SYSTEM_ACTION",
                action="screenshot (saved to ~/Pictures & clipboard)",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["toggle nightlight", "night light", "toggle night light"]):
            ok = self._launch_cmd(["omarchy-toggle-nightlight"])
            result.update(
                matched=True,
                intent="SYSTEM_ACTION",
                action="toggle_nightlight",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        # 9. Universal Application Launcher (any app on system)
        if any(phrase in text for phrase in ["open terminal", "launch terminal", "new terminal"]):
            ok = self.hypr.exec_app("omarchy-default-terminal")
            result.update(
                matched=True,
                intent="APP_LAUNCH",
                action="launch terminal",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["open browser", "launch browser"]):
            ok = self.hypr.exec_app("omarchy-default-browser")
            result.update(
                matched=True,
                intent="APP_LAUNCH",
                action="launch browser",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        if any(phrase in text for phrase in ["open editor", "open neovim", "launch editor"]):
            ok = self.hypr.exec_app("omarchy-default-editor")
            result.update(
                matched=True,
                intent="APP_LAUNCH",
                action="launch editor",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
            return result

        m_open = re.search(
            r"\b(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+)\b",
            text,
        )
        if m_open:
            app_query = m_open.group(1).strip()
            if app_query not in ("workspace", "desktop") and not re.match(r"^(?:workspace|desktop)\s+\d+", app_query):
                app_match = self.apps.find_app(app_query)
                if app_match:
                    launch_res = self.apps.launch(app_query)
                    result.update(
                        matched=True,
                        intent="APP_LAUNCH",
                        action=f"launch {app_match['name']}",
                        success=launch_res.get("success", False),
                        speech=f"Opening {app_match['name']}." if launch_res.get("success") else None,
                    )
                    if launch_res.get("success") and self.system2 and self.system2.tts:
                        self.system2.tts.speak(f"Opening {app_match['name']}.", block=False)
                    result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                    return result

        # 6. Fallback: Unmatched intent -> escalate to System 2 Agent if configured
        if laya_eval.get("available") and laya_eval.get("intent") == "ESCALATE_GENERATIVE" and laya_eval.get("confident"):
            if self.system2:
                agent_res = self.system2.query(raw_text, speak=True)
                result.update(
                    matched=True,
                    intent="ESCALATE_GENERATIVE",
                    action="system2_agent_query",
                    success=agent_res.get("status") == "ok",
                    response=agent_res.get("response"),
                    requires_clarification=agent_res.get("requires_clarification", False),
                    agent_result=agent_res,
                )
            else:
                result.update(
                    matched=True,
                    intent="ESCALATE_GENERATIVE",
                    action="escalate_to_system2",
                    success=True,
                )
        elif self.system2:
            agent_res = self.system2.query(raw_text, speak=True)
            result.update(
                matched=True,
                intent="ESCALATE_GENERATIVE",
                action="system2_agent_query",
                success=agent_res.get("status") == "ok",
                response=agent_res.get("response"),
                requires_clarification=agent_res.get("requires_clarification", False),
                agent_result=agent_res,
            )

        result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
        return result

    def _launch_cmd(self, cmd: list[str]) -> bool:
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception:
            return False
