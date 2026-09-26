"""System 2 Deliberative Reasoning Tier & Agent Bridge for Eva desktop automation suite.

Bridges ambiguous, generative, or multi-step voice commands to Omarchy's
pre-configured agent CLIs (Gemini, Claude, Codex) with real-time Hyprland
telemetry and local Kokoro-82M neural TTS feedback.
"""

import json
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional

from core.capabilities import capabilities_registry
from core.tts_kokoro import KokoroTTS
from core.vision_capture import VisionCapture


def strip_ansi_and_banners(text: str) -> str:
    """Remove ANSI terminal color codes and CLI banner lines from agent output."""
    # Strip ANSI escape codes
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    clean = ansi_escape.sub("", text)

    lines = clean.splitlines()
    filtered = []
    for line in lines:
        l = line.strip()
        # Filter common CLI banner warnings
        if not l:
            continue
        if l.startswith("Warning:") or l.startswith("YOLO mode") or l.startswith("[STARTUP]"):
            continue
        if l.startswith("Not logged in") or "Visual rendering will be limited" in l:
            continue
        filtered.append(line)

    return "\n".join(filtered).strip()


class System2Agent:
    """Deliberative reasoning agent bridging voice interactions to Omarchy Agent CLIs."""

    def __init__(
        self,
        agent_name: Optional[str] = None,
        tts: Optional[KokoroTTS] = None,
        enable_tts: bool = True,
    ):
        self.tts = tts or (KokoroTTS(lazy_init=True) if enable_tts else None)
        self.enable_tts = enable_tts
        self.agent_name = agent_name or self._detect_default_agent()
        self.vision = VisionCapture()

        # Multi-turn conversational memory
        self.history: List[Dict[str, str]] = []
        self.max_history = 6  # Last 3 user/assistant turns

    def _detect_default_agent(self) -> str:
        """Detect configured default agent from Omarchy environment."""
        env_agent = os.environ.get("EVA_AGENT")
        if env_agent:
            return env_agent

        try:
            res = subprocess.run(
                ["omarchy-default-agent"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            detected = res.stdout.strip().lower()
            if detected in ("gemini", "claude", "codex", "opencode"):
                return detected
        except Exception:
            pass

        # Check binaries in PATH
        for cand in ["gemini", "claude", "codex"]:
            if subprocess.run(["which", cand], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return cand

        return "gemini"

    def get_desktop_telemetry(self) -> Dict[str, Any]:
        """Collect live Hyprland window, workspace, and desktop telemetry."""
        telemetry: Dict[str, Any] = {
            "active_window": None,
            "open_windows": [],
            "workspaces": [],
        }

        # 1. Active window
        try:
            p = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if p.returncode == 0 and p.stdout.strip():
                data = json.loads(p.stdout)
                telemetry["active_window"] = {
                    "title": data.get("title", ""),
                    "class": data.get("class", ""),
                    "workspace": data.get("workspace", {}).get("name", "1"),
                }
        except Exception:
            pass

        # 2. Open clients
        try:
            p = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if p.returncode == 0 and p.stdout.strip():
                clients = json.loads(p.stdout)
                telemetry["open_windows"] = [
                    {
                        "title": c.get("title", ""),
                        "class": c.get("class", ""),
                        "workspace": c.get("workspace", {}).get("name", ""),
                    }
                    for c in clients
                    if c.get("mapped") and not c.get("hidden")
                ]
        except Exception:
            pass

        # 3. Workspaces
        try:
            p = subprocess.run(
                ["hyprctl", "workspaces", "-j"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if p.returncode == 0 and p.stdout.strip():
                wss = json.loads(p.stdout)
                telemetry["workspaces"] = [
                    {"id": w.get("id"), "name": w.get("name"), "windows": w.get("windows", 0)}
                    for w in wss
                ]
        except Exception:
            pass

        return telemetry

    def format_system_prompt(self, telemetry: Dict[str, Any]) -> str:
        """Construct system prompt with situational desktop telemetry and grounded capabilities."""
        act = telemetry.get("active_window")
        act_desc = f"{act['title']} (class: {act['class']}, workspace: {act['workspace']})" if act else "Desktop background"

        open_wins = telemetry.get("open_windows", [])
        wins_desc = ", ".join([f"{w['class']} ('{w['title'][:30]}')" for w in open_wins[:6]]) or "None"
        cap_context = capabilities_registry.format_system_prompt_context()

        prompt = f"""You are Eva, the voice-enabled AI assistant embedded directly into Omarchy Linux running the Hyprland Wayland compositor.
The user is speaking to you via real-time voice control.

Current Desktop State:
- Focused Window: {act_desc}
- Other Visible Windows: {wins_desc}

{cap_context}

Guidelines for Spoken Output:
1. Answer directly and concisely. Keep responses conversational and brief (1 to 3 spoken sentences) unless the user specifically asks for long explanations or code.
2. Absolutely DO NOT use markdown formatting (no asterisks **, no bullet points -, no markdown headings #) because your response is being converted directly into speech via Kokoro neural text-to-speech.
3. If the user's command is ambiguous or requires confirmation before taking a risky action, ask a clear, direct question.
"""
        return prompt

    def query(
        self,
        user_text: str,
        speak: bool = True,
        block_speech: bool = False,
    ) -> Dict[str, Any]:
        """Execute deliberative reasoning over user voice command using Omarchy Agent CLI."""
        # Detect if user is asking to visually inspect the screen
        visual_triggers = [
            "what's on my screen",
            "what is on my screen",
            "what do you see",
            "look at my screen",
            "look at the screen",
            "read my screen",
            "read this error",
            "what is displayed",
            "describe the screen",
            "see this",
        ]
        if any(trig in user_text.lower() for trig in visual_triggers):
            return self.query_vision(user_text, speak=speak, block_speech=block_speech)

        t_start = time.perf_counter()
        telemetry = self.get_desktop_telemetry()
        system_prompt = self.format_system_prompt(telemetry)

        # Build prompt with history
        history_text = ""
        if self.history:
            history_text = "Recent conversation:\n"
            for turn in self.history[-4:]:
                role = "User" if turn["role"] == "user" else "Eva"
                history_text += f"{role}: {turn['content']}\n"
            history_text += "\n"

        full_prompt = f"{system_prompt}\n{history_text}User: {user_text}\nEva:"

        # Invoke agent CLI backend
        raw_output = ""
        agent_used = self.agent_name

        try:
            if self.agent_name == "gemini":
                cmd = ["gemini", "-p", full_prompt, "--yolo"]
            elif self.agent_name == "claude":
                cmd = ["claude", "-p", full_prompt, "--allow-dangerously-skip-permissions"]
            else:
                cmd = ["gemini", "-p", full_prompt, "--yolo"]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15.0,
            )
            raw_output = proc.stdout if proc.returncode == 0 else (proc.stdout or proc.stderr)
        except subprocess.TimeoutExpired:
            raw_output = "I apologize. The agent query timed out."
        except Exception as e:
            raw_output = f"I encountered an error querying the agent: {e}"

        response = strip_ansi_and_banners(raw_output)
        if not response:
            response = "I processed your request, but received an empty response from the agent."

        # Detect if clarification / question is needed
        requires_clarification = (
            response.strip().endswith("?")
            or any(q in response.lower() for q in [
                "did you mean", "would you like", "should i", "which one", "do you want"
            ])
        )

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

        # Record into conversation history
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": response})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        # Spoken synthesis via Kokoro TTS
        speech_result = None
        if speak and self.tts:
            speech_result = self.tts.speak(response, block=block_speech)

        return {
            "status": "ok",
            "agent": agent_used,
            "prompt": user_text,
            "response": response,
            "requires_clarification": requires_clarification,
            "latency_ms": latency_ms,
            "telemetry": telemetry,
            "speech": speech_result,
        }

    def query_vision(
        self,
        user_text: str,
        speak: bool = True,
        block_speech: bool = False,
        mode: str = "fullscreen",
    ) -> Dict[str, Any]:
        """Capture screen framebuffer and query multimodal agent with attached image."""
        t_start = time.perf_counter()
        img_path, vis_latency = self.vision.capture_screen(mode=mode)
        telemetry = self.get_desktop_telemetry()
        system_prompt = self.format_system_prompt(telemetry)

        # Build prompt with image reference
        full_prompt = (
            f"{system_prompt}\n"
            f"Attached Screen Capture: @{img_path}\n\n"
            f"User request: {user_text}\n"
            "Inspect the attached image carefully and provide a concise, direct spoken response (1-3 sentences).\n"
            "Eva:"
        )

        raw_output = ""
        agent_used = self.agent_name

        try:
            if self.agent_name == "gemini":
                cmd = ["gemini", "-p", full_prompt, "--yolo"]
            elif self.agent_name == "claude":
                cmd = ["claude", "-p", full_prompt, "--allow-dangerously-skip-permissions"]
            else:
                cmd = ["gemini", "-p", full_prompt, "--yolo"]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20.0,
            )
            raw_output = proc.stdout if proc.returncode == 0 else (proc.stdout or proc.stderr)
        except subprocess.TimeoutExpired:
            raw_output = "I apologize. The vision analysis query timed out."
        except Exception as e:
            raw_output = f"I encountered an error analyzing the screen image: {e}"

        response = strip_ansi_and_banners(raw_output)
        if not response:
            response = "I looked at your screen, but could not discern any specific details."

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

        # Record into conversation history
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": response})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        # Spoken synthesis via Kokoro TTS
        speech_result = None
        if speak and self.tts:
            speech_result = self.tts.speak(response, block=block_speech)

        return {
            "status": "ok",
            "agent": agent_used,
            "prompt": user_text,
            "response": response,
            "image_path": img_path,
            "vision_latency_ms": vis_latency,
            "latency_ms": latency_ms,
            "telemetry": telemetry,
            "speech": speech_result,
        }

    def clear_history(self):
        """Reset conversational context."""
        self.history.clear()

    def wait_for_playback(self, timeout: Optional[float] = None) -> bool:
        """Wait for active TTS speech playback to complete."""
        if self.tts:
            return self.tts.wait_for_playback(timeout=timeout)
        return True
