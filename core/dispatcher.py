"""Reflex command dispatcher for sub-150ms voice execution on Omarchy."""

import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from core.app_indexer import AppIndexer
from core.capabilities import capabilities_registry
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


def split_compound_commands(text: str) -> List[str]:
    """Split raw speech transcription on multi-action connectors ('and then', 'then', 'and')."""
    # Protected idiomatic phrases that should never be split
    PROTECTED = [
        ("drag and drop", "drag__AND__drop"),
        ("plug and play", "plug__AND__play"),
        ("date and time", "date__AND__time"),
        ("time and date", "time__AND__date"),
        ("rock and roll", "rock__AND__roll"),
    ]
    t = text
    for phrase, token in PROTECTED:
        t = re.sub(re.escape(phrase), token, t, flags=re.IGNORECASE)

    # Split pattern for sequential chaining
    pattern = (
        r"\b(?:and\s+then|after\s+that|followed\s+by)\b"
        r"|\s*;\s*"
        r"|\s*,\s*then\s+"
        r"|\b\s+then\s+\b"
        r"|\b\s+and\s+(?!(?:a\s+half|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|\d+))\b"
    )
    raw_parts = [p.strip() for p in re.split(pattern, t, flags=re.IGNORECASE) if p and p.strip()]

    restored = []
    for p in raw_parts:
        # Strip leading conversational linkers
        clean_p = re.sub(r"^(?:then|and\s+then|also|and)\s+", "", p, flags=re.IGNORECASE).strip()
        for phrase, token in PROTECTED:
            clean_p = clean_p.replace(token, phrase)
        if clean_p:
            restored.append(clean_p)

    return restored if len(restored) > 1 else [text]


GENERIC_WINDOW_WORDS = {"the", "a", "an", "this", "active", "current", "open", "window", "app"}


def is_generic_window_subject(term: str) -> bool:
    """Return True if the term refers to the current/active/open window rather than a specific app."""
    if not term:
        return True
    clean = term.strip().lower()
    words = [w for w in clean.split() if w not in GENERIC_WINDOW_WORDS]
    return len(words) == 0


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

    def _get_another_workspace(self, cur_ws: str) -> str:
        """Determine another active or available workspace to move a window to."""
        try:
            cur_int = int(cur_ws)
        except (ValueError, TypeError):
            cur_int = 1

        wss = self.hypr.get_workspaces()
        ws_ids = []
        for w in wss:
            try:
                wid = int(w.get("id", 0))
                if wid > 0:
                    ws_ids.append(wid)
            except (ValueError, TypeError):
                pass
        ws_ids = sorted(list(set(ws_ids)))

        other_ids = [wid for wid in ws_ids if wid != cur_int]
        if other_ids:
            higher = [wid for wid in other_ids if wid > cur_int]
            return str(higher[0] if higher else other_ids[0])
        else:
            return str(cur_int + 1 if cur_int > 0 else 2)

    def _resolve_target_workspace(self, target_raw: str, cur_ws: str) -> str:
        """Resolve a raw target workspace specification (numeric, relative, or dynamic) to a workspace ID."""
        t = target_raw.strip().lower()
        if t.isdigit():
            return t
        if t in ("another", "other", "different", "a different"):
            return self._get_another_workspace(cur_ws)
        if t in ("next", "the next"):
            try:
                return str(int(cur_ws) + 1)
            except ValueError:
                return "e+1"
        if t in ("previous", "prev", "the previous"):
            try:
                return str(max(1, int(cur_ws) - 1))
            except ValueError:
                return "e-1"
        return "1"

    def dispatch_text(self, raw_text: str, execute: bool = True) -> Dict[str, Any]:
        """Parse raw speech transcription and execute matching reflex command (or compound sequence)."""
        t_start = time.perf_counter()

        # 1. Check for compound command splitting (e.g. "open spotify and pause music")
        parts = split_compound_commands(raw_text)
        if len(parts) > 1:
            can_all_reflex = True
            dry_results = []
            for part in parts:
                res_dry = self._dispatch_single(part, execute=False)
                if not res_dry.get("matched") or res_dry.get("intent") == "ESCALATE_GENERATIVE":
                    can_all_reflex = False
                    break
                dry_results.append(res_dry)

            if can_all_reflex:
                if not execute:
                    actions = [r.get("action", "") for r in dry_results if r.get("action")]
                    return {
                        "input": raw_text,
                        "normalized": normalize_numbers(raw_text.strip().lower()),
                        "matched": True,
                        "intent": "COMPOUND_REFLEX",
                        "action": " -> ".join(actions),
                        "success": True,
                        "sub_results": dry_results,
                    }

                sub_results = []
                for part in parts:
                    sub_res = self._dispatch_single(part, execute=True)
                    sub_results.append(sub_res)

                actions = [r.get("action", "") for r in sub_results if r.get("action")]
                speeches = [r.get("speech", "") for r in sub_results if r.get("speech")]
                combined_action = " -> ".join(actions)
                combined_speech = " ".join(speeches) if speeches else None

                if combined_speech and self.system2 and self.system2.tts:
                    self.system2.tts.speak(combined_speech, block=False)

                return {
                    "input": raw_text,
                    "normalized": normalize_numbers(raw_text.strip().lower()),
                    "matched": True,
                    "intent": "COMPOUND_REFLEX",
                    "action": combined_action,
                    "success": all(r.get("success", False) for r in sub_results),
                    "speech": combined_speech,
                    "sub_results": sub_results,
                    "latency_ms": round((time.perf_counter() - t_start) * 1000, 2),
                    "laya": {"available": True, "intent": "COMPOUND_REFLEX", "confidence": 1.0, "confident": True},
                }
            elif self.system2:
                if not execute:
                    return {
                        "input": raw_text,
                        "normalized": normalize_numbers(raw_text.strip().lower()),
                        "matched": True,
                        "intent": "ESCALATE_GENERATIVE",
                        "action": "system2_agent_query",
                        "success": True,
                    }
                agent_res = self.system2.query(raw_text, speak=True)
                return {
                    "input": raw_text,
                    "normalized": normalize_numbers(raw_text.strip().lower()),
                    "matched": True,
                    "intent": "ESCALATE_GENERATIVE",
                    "action": "system2_agent_query",
                    "success": agent_res.get("status") == "ok",
                    "response": agent_res.get("response"),
                    "requires_clarification": agent_res.get("requires_clarification", False),
                    "agent_result": agent_res,
                    "latency_ms": round((time.perf_counter() - t_start) * 1000, 2),
                    "laya": {"available": True, "intent": "ESCALATE_GENERATIVE", "confidence": 1.0, "confident": True},
                }

        # Otherwise execute single command directly
        return self._dispatch_single(raw_text, execute=execute)

    dispatch = dispatch_text

    def _dispatch_single(self, raw_text: str, execute: bool = True) -> Dict[str, Any]:
        """Evaluate and optionally execute a single atomic voice command."""
        t_start = time.perf_counter()
        text = raw_text.strip().lower()
        text = normalize_numbers(text)

        # Laya decision model prediction
        laya_eval = self.laya.predict(raw_text) if execute else {"available": False}

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

        # ------------------------------------------------------------- 0a. Jarvis Identity & Persona
        identity_patterns = [
            r"\bwho\s+are\s+you\b",
            r"\bwhat\s+are\s+you\b(?!\s+(?:capable|doing))",
            r"\bidentify\s+yourself\b",
            r"\btell\s+me\s+about\s+yourself\b",
            r"\bwho\s+made\s+you\b",
            r"\bwhat\s+is\s+jarvis\b",
            r"\bintroduce\s+yourself\b",
            r"\bgive\s+me\s+an\s+overview\s+of\s+jarvis\b",
        ]
        if any(re.search(p, text) for p in identity_patterns):
            id_info = capabilities_registry.get_identity()
            speech = id_info["speech"]
            if not execute:
                result.update(matched=True, intent="JARVIS_IDENTITY", action="identify_jarvis", success=True)
                return result
            result.update(
                matched=True,
                intent="JARVIS_IDENTITY",
                action="identify_jarvis",
                success=True,
                speech=speech,
                identity=id_info,
            )
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 0b. Domain-Specific Capability Drill-Down
        # e.g., "what can you do with audio", "tell me about windows", "audio capabilities", "how does vision work"
        m_domain_q = re.search(
            r"\b(?:what\s+can\s+you\s+do\s+(?:with|for|in|about)|tell\s+me\s+about|how\s+does|what\s+are\s+your\s+capabilities\s+(?:with|for|in|about)?)\s+([a-zA-Z0-9_\-\s]+?)(?:\s+capabilities|\s+work)?\b",
            text,
        )
        domain_matched = None
        if m_domain_q:
            cand = m_domain_q.group(1).strip()
            if cand not in ("yourself", "this", "it", "you"):
                domain_matched = capabilities_registry.resolve_domain(cand)

        if not domain_matched:
            m_cap_suffix = re.search(r"\b([a-zA-Z0-9_\-]+)\s+capabilities\b", text)
            if m_cap_suffix:
                cand = m_cap_suffix.group(1).strip()
                if cand not in ("your", "all", "general"):
                    domain_matched = capabilities_registry.resolve_domain(cand)

        if domain_matched:
            domain_info = capabilities_registry.get_domain_details(domain_matched)
            if domain_info:
                speech = domain_info["speech"]
                if not execute:
                    result.update(matched=True, intent="JARVIS_CAPABILITIES", action=f"capabilities_domain_{domain_matched}", success=True)
                    return result
                result.update(
                    matched=True,
                    intent="JARVIS_CAPABILITIES",
                    action=f"capabilities_domain_{domain_matched}",
                    success=True,
                    speech=speech,
                    domain_details=domain_info,
                )
                if self.system2 and self.system2.tts:
                    self.system2.tts.speak(speech, block=False)
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result

        # ------------------------------------------------------------- 0c. General Capabilities Overview
        general_cap_patterns = [
            r"\bwhat\s+can\s+you\s+do\b",
            r"\bwhat\s+are\s+you\s+capable\s+of\b",
            r"\bwhat\s+are\s+your\s+capabilities\b",
            r"\blist\s+capabilities\b",
            r"\bshow\s+capabilities\b",
            r"\bwhat\s+features\s+do\s+you\s+have\b",
            r"\bwhat\s+commands\s+do\s+you\s+support\b",
            r"\bwhat\s+commands\s+can\s+i\s+run\b",
            r"^help$",
            r"^help\s+me$",
        ]
        if any(re.search(p, text) for p in general_cap_patterns):
            overview = capabilities_registry.get_overview()
            speech = overview["speech"]
            if not execute:
                result.update(matched=True, intent="JARVIS_CAPABILITIES", action="capabilities_overview", success=True)
                return result
            result.update(
                matched=True,
                intent="JARVIS_CAPABILITIES",
                action="capabilities_overview",
                success=True,
                speech=speech,
                capabilities=overview,
            )
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 0. Visual UI Click
        m_click = re.search(
            r"\b(double\s+click|right\s+click|click|press|tap)\s*(?:on\s+)?(?:the\s+)?(.+)\b",
            raw_text,
            re.IGNORECASE,
        )
        if m_click:
            action_verb = m_click.group(1).lower()
            target_element = m_click.group(2).strip()
            if (
                target_element not in ("play", "pause", "stop", "next", "previous", "mute", "unmute", "scratchpad")
                and not target_element.startswith("workspace")
                and not target_element.startswith("desktop")
            ):
                if not execute:
                    result.update(matched=True, intent="VISUAL_CLICK", action=f"{action_verb} {target_element}", success=True)
                    return result

                is_double = "double" in action_verb
                button_type = "right" if "right" in action_verb else "left"
                res = self.visual.locate_and_click(target_element, button=button_type, double=is_double)
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

        # ------------------------------------------------------------- 1. Move Window to Workspace
        # Matches active window or specific named app/window moving to numeric, relative, or dynamic workspace:
        # e.g.:
        # - "move an open window to another workspace"
        # - "move open window to another workspace"
        # - "move this window to workspace 2"
        # - "move window to next workspace"
        # - "move active window to workspace 3"
        # - "move spotify to workspace 4"
        # - "move discord to another workspace"
        # - "send window to desktop 2"
        # - "put this on workspace 5"
        m_move_win = re.search(
            r"\b(?:move|send|transfer|put|shift)\s+(?:(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+window|\s+app)?\s+)?(?:on|in|to)\s+(?:workspace|desktop)?\s*(\d+|another|other|a\s+different|different|next|previous|prev)(?:\s+workspace|\s+desktop)?\b",
            text,
        )
        if m_move_win:
            raw_subj = (m_move_win.group(1) or "").strip()
            raw_target = m_move_win.group(2).strip()

            if is_generic_window_subject(raw_subj):
                # Moving currently active / open window
                if not execute:
                    result.update(
                        matched=True,
                        intent="HYPR_WINDOW_MOVE",
                        action=f"movetoworkspace {raw_target}",
                        success=True,
                    )
                    return result

                act = self.hypr.get_active_window()
                cur_ws = str(act.get("workspace", {}).get("name") or act.get("workspace", {}).get("id") or "1") if act else "1"
                target_ws = self._resolve_target_workspace(raw_target, cur_ws)
                win_class = act.get("initialClass") or act.get("class") or "window" if act else "window"

                ok = self.hypr.move_window_to_workspace(target_ws)
                self.hypr.focus_workspace(target_ws)
                speech = f"Moved {win_class} to workspace {target_ws}."

                result.update(
                    matched=True,
                    intent="HYPR_WINDOW_MOVE",
                    action=f"movetoworkspace {target_ws}",
                    success=ok,
                    speech=speech,
                )
                if result.get("speech") and self.system2 and self.system2.tts:
                    self.system2.tts.speak(result["speech"], block=False)
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result

            else:
                # Moving a specific named application / window
                target_app_query = raw_subj
                if not execute:
                    result.update(
                        matched=True,
                        intent="HYPR_WINDOW_MOVE",
                        action=f"move_window {target_app_query} -> ws {raw_target}",
                        success=True,
                    )
                    return result

                client = self.hypr.find_open_window(target_app_query, app_indexer=self.apps)
                if client:
                    ws_info = client.get("workspace", {})
                    cur_ws = str(ws_info.get("name") or ws_info.get("id") or "1")
                    app_name = client.get("initialClass") or client.get("class") or target_app_query
                    address = client.get("address", "")
                    target_ws = self._resolve_target_workspace(raw_target, cur_ws)

                    if cur_ws == target_ws:
                        self.hypr.focus_workspace(target_ws)
                        if address:
                            self.hypr.focus_window_address(address)
                        speech = f"{app_name} is already on workspace {target_ws}."
                    else:
                        self.hypr.focus_workspace(cur_ws)
                        if address:
                            self.hypr.focus_window_address(address)
                        ok = self.hypr.move_window_to_workspace(target_ws)
                        self.hypr.focus_workspace(target_ws)
                        speech = f"Moved {app_name} to workspace {target_ws}."

                    result.update(
                        matched=True,
                        intent="HYPR_WINDOW_MOVE",
                        action=f"move_window {target_app_query} -> ws {target_ws}",
                        success=True,
                        speech=speech,
                    )
                else:
                    speech = f"I could not find an open window for {target_app_query}."
                    result.update(
                        matched=True,
                        intent="HYPR_WINDOW_MOVE",
                        action=f"window_not_found {target_app_query}",
                        success=False,
                        speech=speech,
                    )

                if result.get("speech") and self.system2 and self.system2.tts:
                    self.system2.tts.speak(result["speech"], block=False)
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result

        # ------------------------------------------------------------- 2. Targeted Workspace Launch / Open
        # e.g., "open spotify on workspace 4", "launch ghostty in desktop 2", "open terminal in workspace 3"
        m_target_launch = re.search(
            r"\b(?:open|launch|start|run)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:on|in|to)\s+(?:workspace|desktop)\s*(\d+)\b",
            text,
        )
        if m_target_launch:
            target_app_query = m_target_launch.group(1).strip()
            target_ws = m_target_launch.group(2).strip()

            if not execute:
                result.update(matched=True, intent="APP_LAUNCH", action=f"open {target_app_query} on workspace {target_ws}", success=True)
                return result

            client = self.hypr.find_open_window(target_app_query, app_indexer=self.apps)
            if client:
                ws_info = client.get("workspace", {})
                cur_ws = str(ws_info.get("name") or ws_info.get("id") or "1")
                app_name = client.get("initialClass") or client.get("class") or target_app_query
                address = client.get("address", "")

                if cur_ws == target_ws:
                    self.hypr.focus_workspace(target_ws)
                    if address:
                        self.hypr.focus_window_address(address)
                    speech = f"{app_name} is already open on workspace {target_ws}. Focusing."
                else:
                    self.hypr.focus_workspace(cur_ws)
                    if address:
                        self.hypr.focus_window_address(address)
                    self.hypr.move_window_to_workspace(target_ws)
                    self.hypr.focus_workspace(target_ws)
                    speech = f"Moved {app_name} to workspace {target_ws}."

                result.update(
                    matched=True,
                    intent="HYPR_FOCUS",
                    action=f"target_workspace {target_app_query} -> ws {target_ws}",
                    success=True,
                    speech=speech,
                )
            else:
                self.hypr.focus_workspace(target_ws)
                launch_res = self.apps.launch(target_app_query)
                speech = f"Opening {target_app_query} on workspace {target_ws}."
                result.update(
                    matched=True,
                    intent="APP_LAUNCH",
                    action=f"launch {target_app_query} on ws {target_ws}",
                    success=launch_res.get("success", False),
                    speech=speech,
                )

            if result.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(result["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 3. Hyprland Workspace Navigation
        m_ws = re.search(r"\b(?:switch to|go to|jump to|open)?\s*(?:workspace|desktop)\s*(\d+)\b", text)
        if m_ws:
            ws_num = m_ws.group(1)
            if not execute:
                result.update(matched=True, intent="HYPR_WORKSPACE", action=f"workspace {ws_num}", success=True)
                return result
            ok = self.hypr.focus_workspace(ws_num)
            result.update(matched=True, intent="HYPR_WORKSPACE", action=f"workspace {ws_num}", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if "next workspace" in text:
            if not execute:
                result.update(matched=True, intent="HYPR_WORKSPACE", action="workspace +1", success=True)
                return result
            ok = self.hypr.focus_workspace("e+1")
            result.update(matched=True, intent="HYPR_WORKSPACE", action="workspace +1", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if "previous workspace" in text or "prev workspace" in text:
            if not execute:
                result.update(matched=True, intent="HYPR_WORKSPACE", action="workspace -1", success=True)
                return result
            ok = self.hypr.focus_workspace("e-1")
            result.update(matched=True, intent="HYPR_WORKSPACE", action="workspace -1", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["former workspace", "last workspace", "previous used workspace"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WORKSPACE", action="workspace previous", success=True)
                return result
            ok = self.hypr.focus_workspace("previous")
            result.update(matched=True, intent="HYPR_WORKSPACE", action="workspace previous", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 4. Directional Window Navigation & Layout
        # Focus directional: "focus left", "focus right", "focus up", "focus down"
        m_foc_dir = re.search(r"\b(?:focus|move\s+focus)\s+(?:to\s+)?(?:the\s+)?(left|right|up|down)\b", text)
        if m_foc_dir:
            direction = m_foc_dir.group(1)
            if not execute:
                result.update(matched=True, intent="HYPR_FOCUS", action=f"focus {direction}", success=True)
                return result
            ok = self.hypr.focus_direction(direction)
            result.update(matched=True, intent="HYPR_FOCUS", action=f"focus {direction}", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Swap window directional: "swap window left", "swap right"
        m_swap_dir = re.search(r"\b(?:swap|exchange)\s+(?:window\s+)?(?:with\s+)?(?:to\s+)?(?:the\s+)?(left|right|up|down)\b", text)
        if m_swap_dir:
            direction = m_swap_dir.group(1)
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action=f"swap_window {direction}", success=True)
                return result
            ok = self.hypr.swap_window_direction(direction)
            result.update(matched=True, intent="HYPR_WINDOW", action=f"swap_window {direction}", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Move window directional: "move window left", "shift window down"
        m_move_dir = re.search(r"\b(?:move|shift)\s+window\s+(?:to\s+)?(?:the\s+)?(left|right|up|down)\b", text)
        if m_move_dir:
            direction = m_move_dir.group(1)
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action=f"move_window {direction}", success=True)
                return result
            ok = self.hypr.move_window_direction(direction)
            result.update(matched=True, intent="HYPR_WINDOW", action=f"move_window {direction}", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Scratchpad controls
        if any(phrase in text for phrase in ["send to scratchpad", "move to scratchpad", "minimize to scratchpad", "hide window to scratchpad", "move window to scratchpad"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="move_to_scratchpad", success=True)
                return result
            ok = self.hypr.move_to_scratchpad()
            result.update(matched=True, intent="HYPR_WINDOW", action="move_to_scratchpad", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle scratchpad", "show scratchpad", "hide scratchpad", "open scratchpad"]) or text.strip() == "scratchpad":
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="toggle_scratchpad", success=True)
                return result
            ok = self.hypr.toggle_scratchpad()
            result.update(matched=True, intent="HYPR_WINDOW", action="toggle_scratchpad", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle split", "split window", "toggle window split", "change split"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="toggle_split", success=True)
                return result
            ok = self.hypr.toggle_split()
            result.update(matched=True, intent="HYPR_WINDOW", action="toggle_split", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle pseudo", "pseudo window"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="toggle_pseudo", success=True)
                return result
            ok = self.hypr.toggle_pseudo()
            result.update(matched=True, intent="HYPR_WINDOW", action="toggle_pseudo", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 5. Directory & File Shortcuts
        m_dir = re.search(r"\bopen\s+(downloads|pictures|screenshots|documents|home|config|music|videos)\b", text)
        if m_dir:
            dir_target = m_dir.group(1)
            if not execute:
                result.update(matched=True, intent="DIR_SHORTCUT", action=f"open_{dir_target}", success=True)
                return result
            res = self.system.open_directory(dir_target)
            result.update(matched=True, intent="DIR_SHORTCUT", action=f"open_{dir_target}", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 6. Window Inspection & Telemetry Queries
        # "where is <app>"
        m_where = re.search(r"\bwhere\s+is\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+window)?\b", text)
        if m_where:
            query_target = m_where.group(1).strip()
            if not execute:
                result.update(matched=True, intent="HYPR_INSPECTION", action=f"where_is {query_target}", success=True)
                return result
            client = self.hypr.find_open_window(query_target, app_indexer=self.apps)
            if client:
                ws = str(client.get("workspace", {}).get("name") or client.get("workspace", {}).get("id") or "1")
                app_name = client.get("initialClass") or client.get("class") or query_target
                speech = f"{app_name} is open on workspace {ws}."
            else:
                speech = f"{query_target} is not currently running."
            result.update(matched=True, intent="HYPR_INSPECTION", action=f"where_is {query_target}", success=True, speech=speech)
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Active window query
        if any(phrase in text for phrase in ["what window is this", "active window", "current window", "what's currently open", "what window do i have open"]):
            if not execute:
                result.update(matched=True, intent="HYPR_INSPECTION", action="active_window", success=True)
                return result
            act = self.hypr.get_active_window()
            if act:
                c_name = act.get("initialClass") or act.get("class") or "Unknown"
                title = act.get("title", "")
                ws = act.get("workspace", {}).get("name", "unknown")
                speech = f"Current active window is {c_name} on workspace {ws}."
                if title:
                    speech = f"Current window is {c_name}: {title[:40]} on workspace {ws}."
            else:
                speech = "No window is currently active."
            result.update(matched=True, intent="HYPR_INSPECTION", action="active_window", success=True, speech=speech)
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # List all open windows
        if any(phrase in text for phrase in ["what windows are open", "what windows are running", "list open windows", "list windows", "running apps"]):
            if not execute:
                result.update(matched=True, intent="HYPR_INSPECTION", action="list_windows", success=True)
                return result
            clients = self.hypr.get_clients()
            if clients:
                app_names = list(dict.fromkeys([c.get("initialClass") or c.get("class") for c in clients if c.get("class")]))
                speech = f"You have {len(clients)} windows open across your workspaces: {', '.join(app_names[:6])}."
            else:
                speech = "No windows are currently open."
            result.update(matched=True, intent="HYPR_INSPECTION", action="list_windows", success=True, speech=speech)
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Which workspace am I on
        if any(phrase in text for phrase in ["what workspace am i on", "which workspace am i on", "current workspace", "what workspace is this"]):
            if not execute:
                result.update(matched=True, intent="HYPR_INSPECTION", action="current_workspace", success=True)
                return result
            ws = self.hypr.get_json("activeworkspace") or {}
            ws_name = str(ws.get("name") or ws.get("id") or "1")
            speech = f"You are currently on workspace {ws_name}."
            result.update(matched=True, intent="HYPR_INSPECTION", action="current_workspace", success=True, speech=speech)
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 7. Media Song & Playing Track Query
        if any(phrase in text for phrase in [
            "what song is this", "what is playing", "what's playing", "current track",
            "current song", "what track is this", "what is currently playing", "who is this song by",
        ]):
            if not execute:
                result.update(matched=True, intent="MEDIA_QUERY", action="current_track", success=True)
                return result
            res = self.system.get_current_track()
            result.update(matched=True, intent="MEDIA_QUERY", action="current_track", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 8. App Launchers & Smart Focus
        # Default Terminal
        if any(phrase in text for phrase in ["open terminal", "launch terminal", "new terminal"]):
            is_new = "new terminal" in text
            if not is_new:
                client = self.hypr.find_open_window("terminal", app_indexer=self.apps)
                if isinstance(client, dict) and "address" in client:
                    ok = self.hypr.focus_window_by_query("terminal")
                    if ok:
                        ws = str(client.get("workspace", {}).get("name") or client.get("workspace", {}).get("id") or "1")
                        app_name = client.get("initialClass") or client.get("class") or "Terminal"
                        msg = f"Switching to {app_name} on workspace {ws}."
                        result.update(matched=True, intent="HYPR_FOCUS", action="focus terminal", success=True, speech=msg)
                        if self.system2 and self.system2.tts:
                            self.system2.tts.speak(msg, block=False)
                        result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                        return result
            if not execute:
                result.update(matched=True, intent="APP_LAUNCH", action="launch terminal", success=True)
                return result
            ok = self.hypr.exec_app("omarchy-default-terminal")
            result.update(matched=True, intent="APP_LAUNCH", action="launch terminal", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Default Browser
        if any(phrase in text for phrase in ["open browser", "launch browser", "new browser"]):
            is_new = "new browser" in text
            if not is_new:
                client = self.hypr.find_open_window("browser", app_indexer=self.apps)
                if isinstance(client, dict) and "address" in client:
                    ok = self.hypr.focus_window_by_query("browser")
                    if ok:
                        ws = str(client.get("workspace", {}).get("name") or client.get("workspace", {}).get("id") or "1")
                        app_name = client.get("initialClass") or client.get("class") or "Browser"
                        msg = f"Switching to {app_name} on workspace {ws}."
                        result.update(matched=True, intent="HYPR_FOCUS", action="focus browser", success=True, speech=msg)
                        if self.system2 and self.system2.tts:
                            self.system2.tts.speak(msg, block=False)
                        result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                        return result
            if not execute:
                result.update(matched=True, intent="APP_LAUNCH", action="launch browser", success=True)
                return result
            ok = self.hypr.exec_app("omarchy-default-browser")
            result.update(matched=True, intent="APP_LAUNCH", action="launch browser", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Default Editor
        if any(phrase in text for phrase in ["open editor", "launch editor", "new editor"]):
            is_new = "new editor" in text
            if not is_new:
                client = self.hypr.find_open_window("editor", app_indexer=self.apps)
                if isinstance(client, dict) and "address" in client:
                    ok = self.hypr.focus_window_by_query("editor")
                    if ok:
                        ws = str(client.get("workspace", {}).get("name") or client.get("workspace", {}).get("id") or "1")
                        app_name = client.get("initialClass") or client.get("class") or "Editor"
                        msg = f"Switching to {app_name} on workspace {ws}."
                        result.update(matched=True, intent="HYPR_FOCUS", action="focus editor", success=True, speech=msg)
                        if self.system2 and self.system2.tts:
                            self.system2.tts.speak(msg, block=False)
                        result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                        return result
            if not execute:
                result.update(matched=True, intent="APP_LAUNCH", action="launch editor", success=True)
                return result
            ok = self.hypr.exec_app("omarchy-default-editor")
            result.update(matched=True, intent="APP_LAUNCH", action="launch editor", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Focus explicit app window: "focus neovim", "focus obsidian", "bring up spotify"
        m_focus_explicit = re.search(r"\b(?:focus|bring\s+up|switch\s+to)\s+([a-zA-Z0-9_\-]+)\b", text)
        if m_focus_explicit and m_focus_explicit.group(1) not in ("workspace", "desktop", "scratchpad"):
            target_app = m_focus_explicit.group(1)
            if not execute:
                result.update(matched=True, intent="HYPR_FOCUS", action=f"focus {target_app}", success=True)
                return result
            ok = self.hypr.focus_window_by_query(target_app)
            if ok:
                client = self.hypr.find_open_window(target_app, app_indexer=self.apps)
                ws = str(client.get("workspace", {}).get("name") or client.get("workspace", {}).get("id") or "1") if isinstance(client, dict) else "1"
                app_name = client.get("initialClass") or client.get("class") or target_app if isinstance(client, dict) else target_app
                msg = f"Switching to {app_name} on workspace {ws}."
                result.update(matched=True, intent="HYPR_FOCUS", action=f"focus {target_app}", success=True, speech=msg)
                if self.system2 and self.system2.tts:
                    self.system2.tts.speak(msg, block=False)
                result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                return result

        # Smart App Focus or Launch: "open obsidian", "show me spotify", "see spotify"
        m_app = re.search(
            r"\b(?:open|launch|start|run|show\s+me|show|see)\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)(?:\s+window)?\b",
            text,
        )
        if m_app:
            candidate_app = m_app.group(1).strip()
            if (
                candidate_app not in (
                    "workspace", "desktop", "scratchpad", "music", "video", "audio", "mic",
                    "microphone", "downloads", "pictures", "screenshots", "documents", "home",
                    "config", "bar", "top bar", "wifi", "bluetooth", "dnd", "clipboard",
                    "window", "this window", "this", "nightlight", "night light",
                )
                and not candidate_app.startswith("workspace ")
                and not candidate_app.startswith("desktop ")
            ):
                is_explicit_new = any(k in text for k in ("new ", "another ", "fresh "))

                if not execute:
                    result.update(matched=True, intent="HYPR_FOCUS" if not is_explicit_new else "APP_LAUNCH", action=f"app {candidate_app}", success=True)
                    return result

                # 1. If not explicit "new", check if open window actually exists
                if not is_explicit_new:
                    client = self.hypr.find_open_window(candidate_app, app_indexer=self.apps)
                    if isinstance(client, dict) and "address" in client:
                        ok = self.hypr.focus_window_by_query(candidate_app)
                        if ok:
                            app_name = client.get("initialClass") or client.get("class") or candidate_app
                            ws = str(client.get("workspace", {}).get("name") or client.get("workspace", {}).get("id") or "1")
                            msg = f"Switching to {app_name} on workspace {ws}."
                            result.update(matched=True, intent="HYPR_FOCUS", action=f"focus {candidate_app}", success=True, speech=msg)
                            if self.system2 and self.system2.tts:
                                self.system2.tts.speak(msg, block=False)
                            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                            return result

                # 2. Launch via AppIndexer
                app_match = self.apps.find_app(candidate_app)
                if app_match:
                    launch_res = self.apps.launch(candidate_app)
                    speech = f"Launching {app_match['name']}."
                    result.update(
                        matched=True,
                        intent="APP_LAUNCH",
                        action=f"launch {app_match['name']}",
                        success=launch_res.get("success", False),
                        speech=speech,
                    )
                    if self.system2 and self.system2.tts:
                        self.system2.tts.speak(speech, block=False)
                    result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
                    return result

        # ------------------------------------------------------------- 9. Window and Application Closing
        m_close = re.search(
            r"\b(?:close|quit|kill|exit)\s+(?:the\s+)?(?:application\s+|app\s+|program\s+)?([a-zA-Z0-9_\-\.\s]+)\b",
            text,
        )
        if m_close:
            target_close = m_close.group(1).strip()
            if not execute:
                result.update(matched=True, intent="APP_CLOSE", action=f"close {target_close}", success=True)
                return result

            if target_close in ("window", "this window", "this", "active", "active window", "window now", "current window"):
                ok = self.hypr.close_window()
                result.update(matched=True, intent="HYPR_WINDOW", action="close_window", success=ok)
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

        # Fullscreen & Window Sizing
        if "screenshot" not in text and "capture" not in text and any(
            phrase in text for phrase in ["fullscreen", "make fullscreen", "toggle fullscreen", "full screen", "maximize"]
        ):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="fullscreen", success=True)
                return result
            ok = self.hypr.toggle_fullscreen()
            result.update(matched=True, intent="HYPR_WINDOW", action="fullscreen", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle float", "toggle floating", "float window", "make floating"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="togglefloating", success=True)
                return result
            ok = self.hypr.toggle_floating()
            result.update(matched=True, intent="HYPR_WINDOW", action="togglefloating", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["center window", "center this window", "center active window"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="center_window", success=True)
                return result
            ok = self.system.center_active_window()
            result.update(matched=True, intent="HYPR_WINDOW", action="center_window", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["pin window", "unpin window", "toggle pin"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="pin_window", success=True)
                return result
            ok = self.system.pin_active_window()
            result.update(matched=True, intent="HYPR_WINDOW", action="pin_window", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["move window to next monitor", "move window to other monitor", "send window to next monitor"]):
            if not execute:
                result.update(matched=True, intent="HYPR_WINDOW", action="move_to_next_monitor", success=True)
                return result
            ok = self.system.move_window_to_monitor("+1")
            result.update(matched=True, intent="HYPR_WINDOW", action="move_to_next_monitor", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 10. Media & Audio Controls
        if any(phrase in text for phrase in ["pause music", "pause the music", "pause song", "pause audio", "pause video", "pause playback", "hold playback", "stop playback"]) or re.search(r"\bpause\b", text):
            if not execute:
                result.update(matched=True, intent="MEDIA_CONTROL", action="pause", success=True)
                return result
            ok = self.media.pause()
            result.update(matched=True, intent="MEDIA_CONTROL", action="pause", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["play music", "play song", "resume music", "resume video", "resume playback", "unpause"]) or (re.search(r"\b(?:play|resume)\b", text) and "display" not in text and "gameplay" not in text):
            if not execute:
                result.update(matched=True, intent="MEDIA_CONTROL", action="play", success=True)
                return result
            ok = self.media.play()
            result.update(matched=True, intent="MEDIA_CONTROL", action="play", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle playback", "play pause", "toggle media", "toggle music", "toggle video"]):
            if not execute:
                result.update(matched=True, intent="MEDIA_CONTROL", action="play_pause", success=True)
                return result
            ok = self.media.play_pause()
            result.update(matched=True, intent="MEDIA_CONTROL", action="play_pause", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["next track", "next song", "skip track", "skip song", "skip"]):
            if not execute:
                result.update(matched=True, intent="MEDIA_CONTROL", action="next", success=True)
                return result
            ok = self.media.next_track()
            result.update(matched=True, intent="MEDIA_CONTROL", action="next", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["previous track", "previous song", "prev track"]):
            if not execute:
                result.update(matched=True, intent="MEDIA_CONTROL", action="previous", success=True)
                return result
            ok = self.media.previous_track()
            result.update(matched=True, intent="MEDIA_CONTROL", action="previous", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Volume adjustments
        if any(phrase in text for phrase in ["volume up", "turn it up", "louder", "increase volume"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="volume_up 5%", success=True)
                return result
            ok = self.media.volume_up(5)
            result.update(matched=True, intent="AUDIO_CONTROL", action="volume_up 5%", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["volume down", "turn it down", "quieter", "decrease volume", "lower volume"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="volume_down 5%", success=True)
                return result
            ok = self.media.volume_down(5)
            result.update(matched=True, intent="AUDIO_CONTROL", action="volume_down 5%", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["max volume", "maximum volume", "full volume", "volume 100"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="set_volume 100%", success=True)
                return result
            ok = self.media.set_volume(100)
            result.update(matched=True, intent="AUDIO_CONTROL", action="set_volume 100%", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["half volume", "volume 50"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="set_volume 50%", success=True)
                return result
            ok = self.media.set_volume(50)
            result.update(matched=True, intent="AUDIO_CONTROL", action="set_volume 50%", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        m_vol = re.search(r"\b(?:set volume to|volume)\s*(\d+)(?:\s*percent|%)?\b", text)
        if m_vol:
            val = int(m_vol.group(1))
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action=f"set_volume {val}%", success=True)
                return result
            ok = self.media.set_volume(val)
            result.update(matched=True, intent="AUDIO_CONTROL", action=f"set_volume {val}%", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["unmute mic", "unmute microphone"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="mic_mute 0", success=True)
                return result
            ok = self.media.set_mic_mute(False)
            result.update(matched=True, intent="AUDIO_CONTROL", action="mic_mute 0", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["mute mic", "mute microphone", "silence mic"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="mic_mute 1", success=True)
                return result
            ok = self.media.set_mic_mute(True)
            result.update(matched=True, intent="AUDIO_CONTROL", action="mic_mute 1", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if text in ["mute", "unmute", "toggle mute", "mute audio", "unmute audio", "mute sound", "unmute sound", "mute volume", "unmute volume"]:
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="toggle_mute", success=True)
                return result
            ok = self.media.toggle_mute_output()
            result.update(matched=True, intent="AUDIO_CONTROL", action="toggle_mute", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 10b. Audio Device & Microphone Routing
        # Switch Audio Output Device
        # e.g., "switch audio output device to headset", "switch audio output to speakers", "change audio to headphones", "switch output to kraken"
        m_audio_out = re.search(
            r"\b(?:switch|change|set)\s+(?:the\s+)?(?:audio\s+output|sound\s+output|playback\s+device|output\s+device|audio\s+device|output)\s+(?:device\s+)?to\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+)\b",
            raw_text,
            re.IGNORECASE,
        )
        if not m_audio_out:
            m_audio_out_alt = re.search(
                r"\b(?:switch|change)\s+to\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:audio|speakers|headphones|headset|sound)\b",
                raw_text,
                re.IGNORECASE,
            )
            if m_audio_out_alt and not any(kw in m_audio_out_alt.group(1).lower() for kw in ("workspace", "desktop", "tab", "window")):
                m_audio_out = m_audio_out_alt

        if m_audio_out:
            target_dev = m_audio_out.group(1).strip()
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action=f"switch_audio_output {target_dev}", success=True)
                return result
            res = self.system.switch_audio_output(target_dev)
            result.update(matched=True, intent="AUDIO_CONTROL", action=f"switch_audio_output {target_dev}", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Switch Audio Input / Microphone
        # e.g., "switch microphone to headset", "switch mic to webcam", "change audio input to usb mic", "set microphone to vitade"
        m_audio_in = re.search(
            r"\b(?:switch|change|set)\s+(?:the\s+)?(?:microphone|mic|audio\s+input|input\s+device|input)\s+(?:device\s+)?to\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+)\b",
            raw_text,
            re.IGNORECASE,
        )
        if not m_audio_in:
            m_audio_in_alt = re.search(
                r"\b(?:switch|change)\s+to\s+(?:the\s+)?([a-zA-Z0-9_\-\.\s]+?)\s+(?:mic|microphone|input)\b",
                raw_text,
                re.IGNORECASE,
            )
            if m_audio_in_alt and not any(kw in m_audio_in_alt.group(1).lower() for kw in ("workspace", "desktop", "tab", "window")):
                m_audio_in = m_audio_in_alt

        if m_audio_in:
            target_mic = m_audio_in.group(1).strip()
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action=f"switch_audio_input {target_mic}", success=True)
                return result
            res = self.system.switch_audio_input(target_mic)
            result.update(matched=True, intent="AUDIO_CONTROL", action=f"switch_audio_input {target_mic}", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Enumerate Audio Devices / Mics
        if any(phrase in text for phrase in ["list audio devices", "list sound devices", "list audio outputs", "what audio devices", "audio devices"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="list_audio_devices", success=True)
                return result
            res = self.system.list_audio_devices_speech("all")
            result.update(matched=True, intent="AUDIO_CONTROL", action="list_audio_devices", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["list microphones", "list mics", "list audio inputs", "what microphones", "available microphones"]):
            if not execute:
                result.update(matched=True, intent="AUDIO_CONTROL", action="list_microphones", success=True)
                return result
            res = self.system.list_audio_devices_speech("input")
            result.update(matched=True, intent="AUDIO_CONTROL", action="list_microphones", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 11. Hardware & Connectivity Controls
        # WiFi
        m_wifi_conn = re.search(r"\bconnect\s+(?:to\s+)?(?:wi-fi|wifi)\s+([a-zA-Z0-9_\-\.\s]+)\b", raw_text, re.IGNORECASE)
        if not m_wifi_conn:
            m_wifi_conn = re.search(r"\bconnect\s+to\s+([a-zA-Z0-9_\-\.\s]+?)\s+(?:wi-fi|wifi)\b", raw_text, re.IGNORECASE)
        if m_wifi_conn:
            target_ssid = m_wifi_conn.group(1).strip()
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action=f"wifi_connect {target_ssid}", success=True)
                return result
            res = self.system.connect_wifi(target_ssid)
            result.update(matched=True, intent="DEVICE_CONTROL", action=f"wifi_connect {target_ssid}", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["disconnect wifi", "disconnect from wifi", "disconnect wi-fi", "disconnect from wi-fi"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_disconnect", success=True)
                return result
            res = self.system.disconnect_wifi()
            result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_disconnect", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["list wifi networks", "list wifi", "show wifi networks", "scan wifi", "available wifi", "what wifi networks are available", "what wifi networks"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_list", success=True)
                return result
            res = self.system.list_wifi_networks(rescan="scan" in text)
            result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_list", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["wifi status", "wi-fi status", "what wifi am i connected to", "current wifi"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_status", success=True)
                return result
            res = self.system.get_wifi_status()
            result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_status", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["turn on wifi", "enable wifi", "wifi on", "turn on wi-fi", "enable wi-fi"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_on", success=True)
                return result
            res = self.system.toggle_wifi("on")
            result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_on", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["turn off wifi", "disable wifi", "wifi off", "turn off wi-fi", "disable wi-fi"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_off", success=True)
                return result
            res = self.system.toggle_wifi("off")
            result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_off", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle wifi", "toggle wi-fi"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_toggle", success=True)
                return result
            res = self.system.toggle_wifi("toggle")
            result.update(matched=True, intent="DEVICE_CONTROL", action="wifi_toggle", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Bluetooth
        m_bt_conn = re.search(r"\bconnect\s+(?:to\s+)?bluetooth\s+([a-zA-Z0-9_\-\.\s]+)\b", raw_text, re.IGNORECASE)
        if m_bt_conn:
            target_bt = m_bt_conn.group(1).strip()
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action=f"bluetooth_connect {target_bt}", success=True)
                return result
            res = self.system.connect_bluetooth(target_bt)
            result.update(matched=True, intent="DEVICE_CONTROL", action=f"bluetooth_connect {target_bt}", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["disconnect bluetooth", "disconnect from bluetooth"]):
            m_bt_disc = re.search(r"\bdisconnect\s+(?:from\s+)?bluetooth\s*(.*)$", text)
            target_bt = m_bt_disc.group(1).strip() if m_bt_disc and m_bt_disc.group(1).strip() else None
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_disconnect", success=True)
                return result
            res = self.system.disconnect_bluetooth(target_bt)
            result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_disconnect", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["list bluetooth devices", "list bluetooth", "show bluetooth devices", "paired bluetooth devices", "available bluetooth devices"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_list", success=True)
                return result
            res = self.system.list_bluetooth_devices()
            result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_list", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["turn on bluetooth", "enable bluetooth", "bluetooth on"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_on", success=True)
                return result
            res = self.system.toggle_bluetooth("on")
            result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_on", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["turn off bluetooth", "disable bluetooth", "bluetooth off"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_off", success=True)
                return result
            res = self.system.toggle_bluetooth("off")
            result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_off", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle bluetooth"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_toggle", success=True)
                return result
            res = self.system.toggle_bluetooth("toggle")
            result.update(matched=True, intent="DEVICE_CONTROL", action="bluetooth_toggle", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Do Not Disturb & Notifications
        if any(phrase in text for phrase in ["do not disturb", "silence notifications", "mute notifications", "enable dnd", "toggle dnd"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="toggle_dnd", success=True)
                return result
            res = self.system.toggle_dnd()
            result.update(matched=True, intent="DEVICE_CONTROL", action="toggle_dnd", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Stay Awake / Idle behavior
        if any(phrase in text for phrase in ["stay awake", "prevent sleep", "keep awake", "prevent idle"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="stay_awake", success=True)
                return result
            res = self.system.toggle_idle("stay-awake")
            result.update(matched=True, intent="DEVICE_CONTROL", action="stay_awake", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["allow idle", "normal idle", "restore idle"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="allow_idle", success=True)
                return result
            res = self.system.toggle_idle("allow-idle")
            result.update(matched=True, intent="DEVICE_CONTROL", action="allow_idle", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Top Bar
        if any(phrase in text for phrase in ["toggle bar", "hide bar", "show bar", "toggle top bar"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="toggle_bar", success=True)
                return result
            res = self.system.toggle_bar()
            result.update(matched=True, intent="DEVICE_CONTROL", action="toggle_bar", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Brightness Controls
        m_bright_set = re.search(r"\b(?:set\s+)?brightness\s+(?:to\s+)?(\d+)\s*(?:percent|%)?\b", text)
        if not m_bright_set:
            m_bright_set = re.search(r"\bset\s+(?:the\s+)?(?:screen|display)\s+brightness\s+(?:to\s+)?(\d+)\s*(?:percent|%)?\b", text)
        if m_bright_set:
            val = int(m_bright_set.group(1))
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action=f"brightness_set {val}%", success=True)
                return result
            res = self.system.set_brightness(val)
            result.update(matched=True, intent="DEVICE_CONTROL", action=f"brightness_set {val}%", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["brightness up", "increase brightness", "make screen brighter", "brighter screen", "more brightness"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="brightness_up", success=True)
                return result
            res = self.system.adjust_brightness(10)
            result.update(matched=True, intent="DEVICE_CONTROL", action="brightness_up", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["brightness down", "decrease brightness", "dim screen", "dim display", "less brightness", "lower brightness"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="brightness_down", success=True)
                return result
            res = self.system.adjust_brightness(-10)
            result.update(matched=True, intent="DEVICE_CONTROL", action="brightness_down", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["what is the brightness", "current brightness", "screen brightness"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="brightness_get", success=True)
                return result
            res = self.system.get_brightness()
            result.update(matched=True, intent="DEVICE_CONTROL", action="brightness_get", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Display / Monitor Inspection & Scaling
        if any(phrase in text for phrase in ["list displays", "list monitors", "what displays are connected", "show monitors", "display settings", "monitor settings"]):
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action="list_displays", success=True)
                return result
            res = self.system.list_displays()
            result.update(matched=True, intent="DEVICE_CONTROL", action="list_displays", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        m_scale = re.search(r"\bset\s+(?:display\s+)?scale\s+(?:on\s+([a-zA-Z0-9_\-]+)\s+)?to\s+([0-9\.]+)\b", text)
        if m_scale:
            mon_target = m_scale.group(1) or "DP-2"
            scale_val = float(m_scale.group(2))
            if not execute:
                result.update(matched=True, intent="DEVICE_CONTROL", action=f"set_scale {mon_target} {scale_val}", success=True)
                return result
            res = self.system.set_display_scale(mon_target, scale_val)
            result.update(matched=True, intent="DEVICE_CONTROL", action=f"set_scale {mon_target} {scale_val}", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 12. Diagnostics & System Telemetry
        # System Health Overview
        if any(phrase in text for phrase in ["system status", "system health", "jarvis health", "health check", "system overview"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="system_health", success=True)
                return result
            # Consolidate CPU, RAM, Disk, and Temp
            cpu_val = round(self.system.get_top_processes("cpu", 1).get("top_process", {}).get("cpu", 0.0), 1)
            ram = self.system.get_ram_status()
            disk = self.system.get_disk_space()
            temp = self.system.get_cpu_temperature()
            temp_str = f"with temperature at {temp['temperature_c']} degrees Celsius" if temp.get("success") else ""
            speech = f"System status is nominal {temp_str}. Available RAM is {ram.get('available_gb', 'unknown')} gigabytes, and free disk space is {disk.get('free_gb', 'unknown')} gigabytes."
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="system_health", success=True, speech=speech)
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(speech, block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Process Telemetry (Top CPU / Memory without LLM)
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
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action=f"top_{count_val}_{metric_val}", success=True)
                return result
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

        # System Uptime
        if any(phrase in text for phrase in ["system uptime", "how long has the computer been running", "how long has the computer been on", "uptime"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="uptime", success=True)
                return result
            res = self.system.get_uptime()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="uptime", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # CPU Temperature
        if any(phrase in text for phrase in ["cpu temperature", "system temperature", "hardware temperature", "how hot is the computer"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="temperature", success=True)
                return result
            res = self.system.get_cpu_temperature()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="temperature", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Battery
        if any(phrase in text for phrase in ["battery status", "battery level", "battery percentage", "how much battery"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="battery_status", success=True)
                return result
            res = self.system.get_battery_status()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="battery_status", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Disk
        if any(phrase in text for phrase in ["free disk", "disk space", "how much storage", "how much disk space", "disk storage"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="disk_space", success=True)
                return result
            res = self.system.get_disk_space()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="disk_space", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # RAM
        if any(phrase in text for phrase in ["free memory", "free ram", "how much ram", "memory usage", "available memory"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="ram_status", success=True)
                return result
            res = self.system.get_ram_status()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="ram_status", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Time and Date
        if any(phrase in text for phrase in ["what time is it", "current time", "what is the time", "what is the date", "what day is it", "tell me the time"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="time_date", success=True)
                return result
            res = self.system.get_time_date()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="time_date", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # Local IP
        if any(phrase in text for phrase in ["what is my ip", "local ip", "ip address", "my ip address"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_TELEMETRY", action="local_ip", success=True)
                return result
            res = self.system.get_local_ip()
            result.update(matched=True, intent="SYSTEM_TELEMETRY", action="local_ip", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 13. Power & Session Controls
        if any(phrase in text for phrase in ["shut down", "shutdown", "power off", "turn off the computer", "turn off computer"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_POWER", action="shutdown", success=True)
                return result
            res = self.system.power_action("shutdown")
            result.update(matched=True, intent="SYSTEM_POWER", action="shutdown", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["reboot", "restart computer", "restart system", "restart the computer"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_POWER", action="reboot", success=True)
                return result
            res = self.system.power_action("reboot")
            result.update(matched=True, intent="SYSTEM_POWER", action="reboot", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["sleep", "suspend computer", "suspend system", "suspend", "go to sleep"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_POWER", action="suspend", success=True)
                return result
            res = self.system.power_action("suspend")
            result.update(matched=True, intent="SYSTEM_POWER", action="suspend", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["log out", "logout", "exit session"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_POWER", action="logout", success=True)
                return result
            res = self.system.power_action("logout")
            result.update(matched=True, intent="SYSTEM_POWER", action="logout", success=True, speech=res.get("speech"))
            if self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 14. Clipboard
        if any(phrase in text for phrase in ["read clipboard", "what is in my clipboard", "what is on my clipboard", "clipboard content", "what's copied"]):
            if not execute:
                result.update(matched=True, intent="CLIPBOARD", action="read_clipboard", success=True)
                return result
            res = self.system.read_clipboard()
            result.update(matched=True, intent="CLIPBOARD", action="read_clipboard", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["clear clipboard", "empty clipboard"]):
            if not execute:
                result.update(matched=True, intent="CLIPBOARD", action="clear_clipboard", success=True)
                return result
            res = self.system.clear_clipboard()
            result.update(matched=True, intent="CLIPBOARD", action="clear_clipboard", success=res.get("success", False), speech=res.get("speech"))
            if res.get("speech") and self.system2 and self.system2.tts:
                self.system2.tts.speak(res["speech"], block=False)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 15. System Utilities
        if any(phrase in text for phrase in ["lock screen", "lock workstation", "lock computer", "lock"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_ACTION", action="lock_session", success=True)
                return result
            ok = self._launch_cmd(["loginctl", "lock-session"])
            result.update(matched=True, intent="SYSTEM_ACTION", action="lock_session", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["fullscreen screenshot", "full screen screenshot", "capture full screen", "screenshot screen"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_ACTION", action="fullscreen_screenshot", success=True)
                return result
            ok = self._launch_cmd(["omarchy-capture-screenshot", "fullscreen", "slurp"])
            result.update(matched=True, intent="SYSTEM_ACTION", action="fullscreen_screenshot (saved to ~/Pictures & clipboard)", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["take screenshot", "capture screenshot", "screenshot region", "screenshot"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_ACTION", action="screenshot", success=True)
                return result
            ok = self._launch_cmd(["omarchy-capture-screenshot", "smart", "slurp"])
            result.update(matched=True, intent="SYSTEM_ACTION", action="screenshot (saved to ~/Pictures & clipboard)", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        if any(phrase in text for phrase in ["toggle nightlight", "night light", "toggle night light"]):
            if not execute:
                result.update(matched=True, intent="SYSTEM_ACTION", action="toggle_nightlight", success=True)
                return result
            ok = self._launch_cmd(["omarchy-toggle-nightlight"])
            result.update(matched=True, intent="SYSTEM_ACTION", action="toggle_nightlight", success=ok)
            result["latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            return result

        # ------------------------------------------------------------- 16. Fallback: System 2 Reasoning
        if not execute:
            return result

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

    def _launch_cmd(self, cmd: List[str]) -> bool:
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
