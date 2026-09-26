"""Central Capabilities & Knowledge Registry for Eva desktop automation suite.

Serves as the canonical single source of truth for:
1. Eva Identity, persona, and system overview.
2. Capability domains (windows, apps, audio, hardware, system, vision, awareness, reasoning, chaining).
3. Dynamic synchronization with training/schema.yaml (intents, slots, templates, actions).
4. Sub-30ms System 1 Butler-voice spoken responses (concise, conversational, no markdown).
5. Rich CLI formatted tables and summaries.
6. System 2 prompt context injection to ground deliberative agent models.
"""

import os
import re
import textwrap
import time
from typing import Any, Dict, List, Optional

import yaml

from core.config import eva_config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SCHEMA_PATH = os.path.join(REPO_ROOT, "training", "schema.yaml")


# Static Domain metadata with natural Butler spoken descriptions and canonical triggers
DOMAIN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "windows": {
        "title": "Hyprland Windows & Workspaces",
        "description": "Manipulate tiling layouts, switch/move workspaces, directional focus, float, fullscreen, and scratchpad.",
        "spoken": "For windows and workspaces, I can navigate between desktops, move windows, adjust directional focus, toggle fullscreen or floating mode, and manage your scratchpad.",
        "examples": [
            "switch to workspace 3",
            "move window to workspace 2",
            "toggle fullscreen",
            "focus left",
            "toggle scratchpad",
        ],
        "aliases": ["windows", "window", "workspace", "workspaces", "desktop", "desktops", "tiling", "layout", "scratchpad"],
        "schema_intents": ["HYPR_WORKSPACE", "HYPR_WINDOW_MOVE", "HYPR_WINDOW"],
    },
    "apps": {
        "title": "Application Indexing & Smart Focus",
        "description": "Index installed applications, smart focus running instances across workspaces, launch into target workspaces, or terminate apps.",
        "spoken": "For applications, I can launch any installed program, switch to and focus existing instances if they are already running, launch directly into target workspaces, or close windows.",
        "examples": [
            "open spotify",
            "launch ghostty on workspace 4",
            "switch to chrome",
            "close discord",
            "list apps",
        ],
        "aliases": ["apps", "application", "applications", "app", "programs", "launch", "software"],
        "schema_intents": ["HYPR_FOCUS", "APP_LAUNCH", "DIR_SHORTCUT"],
    },
    "audio": {
        "title": "Media Playback & Audio Device Routing",
        "description": "Control MPRIS playback, adjust volume/mute, switch audio output sinks (headset, speakers, HDMI), and switch microphone inputs.",
        "spoken": "For audio, I control media playback and volume, and can instantly route sound between headsets, speakers, or HDMI, as well as switch microphone inputs—all in under 30 milliseconds.",
        "examples": [
            "pause music",
            "set volume to 50 percent",
            "switch audio output to headset",
            "switch microphone to webcam",
            "what song is this",
        ],
        "aliases": ["audio", "sound", "volume", "music", "song", "media", "headset", "microphone", "mic", "speakers", "playback"],
        "schema_intents": ["MEDIA_CONTROL", "MEDIA_QUERY", "AUDIO_CONTROL"],
    },
    "hardware": {
        "title": "Hardware, Network & Display Control",
        "description": "Manage Wi-Fi networks (nmcli), Bluetooth devices (bluetoothctl), dual-mode brightness (laptop & AOC DDC/CI), and display scaling.",
        "spoken": "For hardware, I manage Wi-Fi and Bluetooth connections, adjust internal and external monitor brightness, configure display scaling, and toggle do not disturb.",
        "examples": [
            "connect wifi Baxter",
            "list bluetooth devices",
            "set brightness to 70 percent",
            "display settings",
            "toggle dnd",
        ],
        "aliases": ["hardware", "wifi", "network", "bluetooth", "brightness", "backlight", "display", "displays", "monitors", "devices", "dnd"],
        "schema_intents": ["DEVICE_CONTROL"],
    },
    "system": {
        "title": "System Telemetry, Health & Power",
        "description": "Inspect CPU, memory, disk, battery, temperature, uptime, IP addresses, top processes, lock session, reboot, or power off.",
        "spoken": "For system controls, I provide real-time telemetry on CPU, RAM, disk, battery, uptime, and top processes, plus manage power states like locking, rebooting, and shutting down.",
        "examples": [
            "cpu temperature",
            "top cpu processes",
            "how much memory is used",
            "battery status",
            "lock workstation",
            "reboot",
        ],
        "aliases": ["system", "telemetry", "cpu", "ram", "memory", "battery", "temp", "temperature", "power", "disk", "processes", "uptime"],
        "schema_intents": ["SYSTEM_ACTION"],
    },
    "vision": {
        "title": "Visual Perception & Screen Grounding",
        "description": "Sub-35ms screen capture, semantic OCR and visual description, plus locate and click UI elements and buttons directly.",
        "spoken": "For vision, I capture your screen in under 35 milliseconds, describe what is displayed, read errors, or click directly on UI elements like buttons and menus.",
        "examples": [
            "what is on my screen",
            "read this error",
            "click on save",
            "double click the icon",
            "take a screenshot",
        ],
        "aliases": ["vision", "screen", "look", "see", "click", "perception", "screenshot", "ui click"],
        "schema_intents": ["VISUAL_CLICK"],
    },
    "awareness": {
        "title": "Proactive Machine Intelligence & Sentinel",
        "description": "Background watchdog monitoring system health, CPU/RAM thresholds, low disk space, network drops, and severe weather alerts.",
        "spoken": "For proactive awareness, my background sentinel continuously monitors system health, alerting you autonomously to high temperatures, low disk space, network drops, or severe weather.",
        "examples": [
            "sentinel status",
            "trigger test alert",
            "how is system health",
        ],
        "aliases": ["awareness", "sentinel", "proactive", "alerts", "watchdog", "monitoring", "weather", "alert"],
        "schema_intents": ["AWARENESS_STATUS"],
    },
    "chaining": {
        "title": "Compound Reflex Sequences",
        "description": "Chain multiple actions sequentially with 'and' or 'then' with zero LLM latency.",
        "spoken": "For compound commands, I can execute multiple actions in a single spoken breath, such as taking a screenshot and locking the workstation.",
        "examples": [
            "take a screenshot and lock the screen",
            "open spotify and pause music",
            "switch to workspace 2 and launch terminal",
        ],
        "aliases": ["chaining", "compound", "compound commands", "chains", "multistep", "sequence"],
        "schema_intents": ["COMPOUND_REFLEX"],
    },
    "reasoning": {
        "title": "System 2 Deliberative Reasoning",
        "description": "Escalate complex, generative, coding, or diagnostic inquiries to Omarchy Agent CLIs (Gemini, Claude, Codex) with spoken Kokoro feedback.",
        "spoken": "For complex reasoning, I bridge to background AI agents to answer in-depth technical questions, write code, diagnose system logs, or reason over screen contents.",
        "examples": [
            "why is the bluetooth daemon failing",
            "write a bash script to clean up docker containers",
            "explain quantum computing",
        ],
        "aliases": ["reasoning", "agent", "agents", "deliberative", "system 2", "system2", "llm", "intelligence", "gemini", "claude", "codex"],
        "schema_intents": ["ESCALATE_GENERATIVE"],
    },
}


class EvaCapabilitiesRegistry:
    """Dynamic capability registry and knowledge base synchronized with schema.yaml."""

    def __init__(self, schema_path: str = SCHEMA_PATH):
        self.schema_path = schema_path
        self._schema_mtime: float = 0.0
        self._schema_data: Dict[str, Any] = {}
        self._intents: Dict[str, Any] = {}
        self._total_templates: int = 0
        self._reload_if_needed()

    def _reload_if_needed(self):
        """Check mtime of schema.yaml and reload if updated."""
        if not os.path.exists(self.schema_path):
            return

        try:
            mtime = os.path.getmtime(self.schema_path)
            if mtime != self._schema_mtime:
                with open(self.schema_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._schema_data = data
                self._schema_mtime = mtime
                self._intents = data.get("intents", {})
                total_t = 0
                for intent_meta in self._intents.values():
                    if isinstance(intent_meta, dict):
                        total_t += len(intent_meta.get("templates", []))
                    elif isinstance(intent_meta, list):
                        total_t += len(intent_meta)
                self._total_templates = total_t
        except Exception:
            pass

    @property
    def intents(self) -> Dict[str, Any]:
        self._reload_if_needed()
        return self._intents

    @property
    def total_templates(self) -> int:
        self._reload_if_needed()
        return self._total_templates

    @property
    def total_intents(self) -> int:
        self._reload_if_needed()
        return len(self._intents)

    def get_identity(self) -> Dict[str, Any]:
        """Return canonical persona and identity specification."""
        self._reload_if_needed()
        name = eva_config.get("name", "Eva")
        role = "Voice-enabled desktop AI intelligence embedded directly into Omarchy Linux running Hyprland."
        speech = (
            f"I am {name}, the voice-enabled desktop intelligence embedded directly into Omarchy Linux on Hyprland. "
            "I orchestrate sub-30 millisecond desktop automation, system telemetry, screen vision, hardware routing, "
            "and proactive machine awareness, backed by deliberative agent reasoning when needed."
        )
        return {
            "name": name,
            "role": role,
            "system": "Omarchy Linux (Hyprland / Wayland)",
            "tier1": "System 1 Reflex Dispatcher (<30ms, zero LLM calls)",
            "tier2": "System 2 Deliberative Reasoning (Gemini, Claude, Codex agent CLIs)",
            "voice": f"Kokoro-82M Neural TTS ({eva_config.voice}) with real-time acoustic earcons",
            "ui": "Floating Arc-Reactor HUD overlay and Wayland notifications",
            "total_intents": self.total_intents,
            "total_templates": self.total_templates,
            "speech": speech,
        }

    def get_overview(self) -> Dict[str, Any]:
        """Return high-level summary of capabilities across all domains."""
        self._reload_if_needed()
        domains = list(DOMAIN_DEFINITIONS.keys())
        speech = (
            "I can manage your Hyprland windows and workspaces, launch and switch applications, "
            "control media and route audio inputs and outputs, adjust Wi-Fi, Bluetooth, displays, and brightness, "
            "monitor hardware telemetry and system health, perceive and click on screen elements, "
            "provide proactive alerts, and handle complex reasoning via agent bridges. "
            "You can ask me for details on any of these areas, such as audio, windows, hardware, system, vision, or awareness."
        )
        return {
            "summary": "Full desktop voice automation suite for Omarchy Linux",
            "domains": domains,
            "total_domains": len(domains),
            "total_intents": self.total_intents,
            "total_templates": self.total_templates,
            "speech": speech,
        }

    def list_domains(self) -> List[str]:
        """List canonical capability domain names."""
        return list(DOMAIN_DEFINITIONS.keys())

    def resolve_domain(self, query: str) -> Optional[str]:
        """Fuzzy resolve a spoken or text query to a canonical domain name."""
        q = query.strip().lower()
        if q in DOMAIN_DEFINITIONS:
            return q

        for d_key, meta in DOMAIN_DEFINITIONS.items():
            if q in meta.get("aliases", []):
                return d_key

        for d_key, meta in DOMAIN_DEFINITIONS.items():
            for alias in meta.get("aliases", []):
                if len(alias) > 3 and (alias in q or q in alias):
                    return d_key

        return None

    def get_domain_details(self, domain_or_query: str) -> Optional[Dict[str, Any]]:
        """Get detailed breakdown for a specific capability domain."""
        self._reload_if_needed()
        d_key = self.resolve_domain(domain_or_query)
        if not d_key or d_key not in DOMAIN_DEFINITIONS:
            return None

        meta = DOMAIN_DEFINITIONS[d_key]
        schema_intents = meta.get("schema_intents", [])

        # Gather live templates and actions from schema.yaml
        registered_actions: List[str] = []
        registered_templates: List[str] = []
        slot_definitions: Dict[str, List[Any]] = {}

        for intent_name in schema_intents:
            intent_meta = self._intents.get(intent_name, {})
            if isinstance(intent_meta, dict):
                registered_actions.extend(intent_meta.get("actions", []))
                registered_templates.extend(intent_meta.get("templates", []))
                for s_key, s_vals in intent_meta.get("slots", {}).items():
                    slot_definitions[s_key] = s_vals
            elif isinstance(intent_meta, list):
                registered_templates.extend(intent_meta)

        return {
            "domain": d_key,
            "title": meta.get("title"),
            "description": meta.get("description"),
            "spoken": meta.get("spoken"),
            "examples": meta.get("examples", []),
            "schema_intents": schema_intents,
            "registered_actions": sorted(list(set(registered_actions))),
            "total_templates": len(registered_templates),
            "template_samples": registered_templates[:8],
            "slots": slot_definitions,
            "speech": meta.get("spoken"),
        }

    def format_cli_overview(self) -> str:
        """Format an elegant CLI overview of all Eva capabilities."""
        self._reload_if_needed()
        lines = []
        lines.append("╔════════════════════════════════════════════════════════════════════════════════╗")
        lines.append("║                     OMARCHY EVA CAPABILITIES MATRIX                            ║")
        lines.append("╠════════════════════════════════════════════════════════════════════════════════╣")
        lines.append(f"║ Active Domains: {len(DOMAIN_DEFINITIONS):<2} | Registered Schema Intents: {self.total_intents:<3} | Templates: {self.total_templates:<4} ║")
        lines.append("╠══════════════════╤═════════════════════════════════════════════════════════════╣")
        lines.append("║ Domain           │ Description & Capabilities                                  ║")
        lines.append("╟──────────────────┼─────────────────────────────────────────────────────────────╢")

        for key, meta in DOMAIN_DEFINITIONS.items():
            desc = meta.get("description", "")
            wrapped = textwrap.wrap(desc, width=59) or [desc]
            lines.append(f"║ {key:<16} │ {wrapped[0]:<59} ║")
            for sub_line in wrapped[1:]:
                lines.append(f"║ {'':<16} │ {sub_line:<59} ║")

        lines.append("╚══════════════════╧═════════════════════════════════════════════════════════════╝")
        lines.append("\nRun 'omarchy-eva capabilities <domain>' for deep drill-down and template samples.")
        return "\n".join(lines)

    def format_cli_domain(self, domain_or_query: str) -> str:
        """Format an elegant CLI view for a single capability domain."""
        details = self.get_domain_details(domain_or_query)
        if not details:
            return f"Domain '{domain_or_query}' not recognized. Available: {', '.join(self.list_domains())}"

        lines = []
        lines.append("═" * 78)
        lines.append(f" EVA CAPABILITY: {details['title'].upper()}")
        lines.append("═" * 78)
        lines.append(f"Description: {details['description']}")
        lines.append(f"Spoken Voice: \"{details['spoken']}\"")
        lines.append("")
        lines.append(f"Associated Schema Intents: {', '.join(details['schema_intents']) or 'Dynamic Reflex'}")
        if details['registered_actions']:
            lines.append(f"Registered Actions: {', '.join(details['registered_actions'])}")
        lines.append(f"Total Registered Training Templates: {details['total_templates']}")
        lines.append("")
        lines.append("Voice Command Examples:")
        for ex in details["examples"]:
            lines.append(f"  • \"{ex}\"")

        if details["template_samples"]:
            lines.append("")
            lines.append("Sample Grammar Templates:")
            for tmpl in details["template_samples"]:
                lines.append(f"  - {tmpl}")

        if details["slots"]:
            lines.append("")
            lines.append("Slot Entities:")
            for s_name, s_vals in details["slots"].items():
                vals_str = ", ".join(str(v) for v in s_vals[:8])
                if len(s_vals) > 8:
                    vals_str += f" (+{len(s_vals) - 8} more)"
                lines.append(f"  • {s_name}: [{vals_str}]")

        lines.append("═" * 78)
        return "\n".join(lines)

    def format_system_prompt_context(self) -> str:
        """Construct grounded capability context to inject into System 2 prompt."""
        self._reload_if_needed()
        lines = []
        lines.append("Eva Built-In OS Capabilities (System 1 Reflex & Device Controls):")
        lines.append("You have access to these deterministic capabilities already running on the user's system:")
        for key, meta in DOMAIN_DEFINITIONS.items():
            lines.append(f"- {meta['title']}: {meta['description']}")
            exs = ", ".join(f"'{e}'" for e in meta.get("examples", [])[:3])
            lines.append(f"  Examples: {exs}")
        lines.append(
            f"Total {self.total_intents} registered intent categories and {self.total_templates} training patterns. "
            "When responding to identity or capability inquiries, reference these capabilities accurately."
        )
        return "\n".join(lines)


# Singleton instance for universal import
capabilities_registry = EvaCapabilitiesRegistry()
