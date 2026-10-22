"""High-level System 1 Router Model for Hierarchical Decision Architecture."""

import time
from typing import Any, Dict, List, Optional

from core.app_indexer import AppIndexer
from core.dbus_mpris import DbusMediaControl
from core.decision.base import BaseDecisionEngine, DecisionQuestion, DecisionResult
from core.decision.domains import (
    BrowserDomainModel,
    MediaPlaybackDomainModel,
    ScreenGUIDomainModel,
    SpotifyDomainModel,
    SystemControlDomainModel,
    TerminalDomainModel,
    WindowManagerDomainModel,
)
from core.decision.registry import decision_registry
from core.hyprland_ipc import HyprlandIPC
from core.input_controller import InputController
from core.system_control import SystemControl
from core.vision_capture import VisionCapture
from core.visual_grounding import VisualGrounding


class HierarchicalRouter:
    """High-level System 1 router directing user input to specialized domain models."""

    def __init__(
        self,
        engine: Optional[BaseDecisionEngine] = None,
        hypr: Optional[HyprlandIPC] = None,
        media: Optional[DbusMediaControl] = None,
        apps: Optional[AppIndexer] = None,
        system: Optional[SystemControl] = None,
        vision: Optional[VisionCapture] = None,
        visual: Optional[VisualGrounding] = None,
        input_ctrl: Optional[InputController] = None,
    ):
        self.engine = engine or decision_registry.get()
        self.hypr = hypr or HyprlandIPC()
        self.media = media or DbusMediaControl()
        self.apps = apps or AppIndexer()
        self.system = system or SystemControl()
        self.vision = vision or VisionCapture()
        self.visual = visual or VisualGrounding()
        self.input = input_ctrl or InputController()

        # Instantiate specialized domain models
        self.domains = {
            "spotify": SpotifyDomainModel(engine=self.engine, apps=self.apps),
            "media_playback": MediaPlaybackDomainModel(engine=self.engine, media=self.media),
            "window_manager": WindowManagerDomainModel(engine=self.engine, hypr=self.hypr),
            "terminal": TerminalDomainModel(engine=self.engine, apps=self.apps),
            "web_browser": BrowserDomainModel(engine=self.engine),
            "screen_gui": ScreenGUIDomainModel(
                engine=self.engine,
                vision=self.vision,
                visual_grounding=self.visual,
                input_ctrl=self.input,
            ),
            "system_control": SystemControlDomainModel(engine=self.engine, system=self.system),
        }

    def set_engine(self, engine: BaseDecisionEngine):
        """Update the underlying decision engine across router and all domain models."""
        self.engine = engine
        for domain in self.domains.values():
            domain.engine = engine

    def get_router_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the top-level Clef decision question schema for routing."""
        return {
            "target_domain": DecisionQuestion(
                question_id="target_domain",
                question_type="choice",
                instructions="Route the user request to the single most appropriate specialized application or domain model.",
                criteria={
                    "spotify": "Spotify actions: playing a song or artist on Spotify, searching music on Spotify, queueing music, Spotify player controls",
                    "media_playback": "System-wide media playback controls: pause, resume, skip track, volume up/down, mute audio across active media sources",
                    "window_manager": "Hyprland workspace and window layout: switch workspace, move window, focus directional window, close window, fullscreen, scratchpad",
                    "terminal": "Terminal and shell execution: open terminal, run CLI command, bash scripts",
                    "web_browser": "Web browsing: open website URL, search Google or the web, browser tabs",
                    "screen_gui": "Visual on-screen GUI interaction: click button or icon on screen, type into field, inspect visible desktop UI",
                    "system_control": "System telemetry and hardware: check battery, ram, cpu, disk, wifi, bluetooth, brightness, reboot, shutdown, lock",
                    "generative_fallback": "Complex questions, general knowledge, explanations, reasoning, or unhandled queries requiring System 2 LLM",
                },
            )
        }

    def route_and_execute(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        images: Optional[List[str]] = None,
        execute: bool = True,
    ) -> Dict[str, Any]:
        """Route the user query and execute the corresponding domain model."""
        t_start = time.perf_counter()

        # Compile rich state representation
        history_desc = ""
        if context and context.get("command_history"):
            turns = context["command_history"][-3:]
            history_desc = " | Previous turns: " + "; ".join(
                f"{t.get('input')} -> [{t.get('domain')}:{t.get('action')}]" for t in turns
            )

        active_info = ""
        if context and context.get("active_app"):
            active_info = f" | Active App: {context.get('active_app')}"

        state = f"User Request: {text}{active_info}{history_desc}"

        # 1. High-level routing via Clef-Flash
        router_schema = self.get_router_schema()
        decisions = self.engine.predict(
            state=state,
            questions=router_schema,
            images=images,
            context=context,
        )
        route_res = decisions.get("target_domain")
        domain = route_res.selected_option if route_res else "generative_fallback"
        confidence = route_res.confidence if route_res else 0.5
        router_latency = route_res.latency_ms if route_res else 0.0

        # If routed to generative fallback or confidence too low, escalate to System 2
        if domain == "generative_fallback" or domain not in self.domains:
            return {
                "input": text,
                "domain": "generative_fallback",
                "escalate": True,
                "confidence": confidence,
                "latency_ms": round((time.perf_counter() - t_start) * 1000, 2),
                "router_latency_ms": router_latency,
            }

        # 2. Delegate to specialized leaf domain model
        domain_model = self.domains[domain]
        res = domain_model.execute(
            text=text,
            context=context,
            dry_run=not execute,
        )

        res["input"] = text
        res["escalate"] = False
        res["router_confidence"] = confidence
        res["router_latency_ms"] = router_latency
        res["total_latency_ms"] = round((time.perf_counter() - t_start) * 1000, 2)

        return res
