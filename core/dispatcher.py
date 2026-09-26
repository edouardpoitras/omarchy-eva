"""Reflex command dispatcher for sub-150ms voice execution on Omarchy."""

import os
import re
import subprocess
import time
from typing import Any, Dict, Optional

from core.dbus_mpris import DbusMediaControl
from core.hyprland_ipc import HyprlandIPC
from core.system1_laya import LayaDecisionEngine
from core.system2_agent import System2Agent

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
    ):
        self.hypr = hypr or HyprlandIPC()
        self.media = media or DbusMediaControl()
        self.laya = laya or LayaDecisionEngine()
        self.system2 = system2

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

        # Check for deliberate generative escalation
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

        # 3. Hyprland: Window manipulation
        if any(
            phrase in text
            for phrase in [
                "close window",
                "close this window",
                "close this",
                "kill active",
                "kill window",
                "quit window",
            ]
        ):
            ok = self.hypr.close_window()
            result.update(
                matched=True,
                intent="HYPR_WINDOW",
                action="close_window",
                success=ok,
            )
            result["latency_ms"] = round(
                (time.perf_counter() - t_start) * 1000, 2
            )
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

        # 5. System & App Launchers
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

        # 6. Fallback: Unmatched intent -> escalate to System 2 Agent if configured
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
