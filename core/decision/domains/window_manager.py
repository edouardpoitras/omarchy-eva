"""Specialized Hyprland Window and Workspace Decision Model."""

from typing import Any, Dict, Optional

from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor
from core.hyprland_ipc import HyprlandIPC


class WindowManagerDomainModel:
    """Specialized System 1 model for Hyprland workspace and window actions."""

    def __init__(self, engine: BaseDecisionEngine, hypr: Optional[HyprlandIPC] = None):
        self.engine = engine
        self.hypr = hypr or HyprlandIPC()

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef decision question schema for window management."""
        return {
            "wm_action": DecisionQuestion(
                question_id="wm_action",
                question_type="choice",
                instructions="Determine the window management or workspace action requested by the user.",
                criteria={
                    "switch_workspace": "Switch to another workspace or desktop by number or relative index",
                    "move_window": "Move the active window or an application to another workspace",
                    "focus_direction": "Shift window focus directionally (left, right, up, down)",
                    "focus_app": "Focus an open window belonging to a specific application",
                    "close_window": "Close the active window or a specified application window",
                    "toggle_fullscreen": "Toggle fullscreen mode for the active window",
                    "toggle_floating": "Toggle floating or tiling state for the window",
                    "toggle_scratchpad": "Toggle the special scratchpad workspace",
                },
            )
        }

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the window management action."""
        schema = self.get_question_schema()
        decisions = self.engine.predict(state=text, questions=schema, context=context)
        action_res = decisions.get("wm_action")
        action = action_res.selected_option if action_res else "switch_workspace"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_workspace_tokens(text)

        if dry_run:
            return {
                "domain": "window_manager",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action == "switch_workspace":
            ws = tokens.get("workspace") or "1"
            if ws in ("next", "+1"):
                success = self.hypr.switch_workspace("m+1")
                speech = "Switched to next workspace."
            elif ws in ("prev", "previous", "-1"):
                success = self.hypr.switch_workspace("m-1")
                speech = "Switched to previous workspace."
            else:
                success = self.hypr.switch_workspace(str(ws))
                speech = f"Switched to workspace {ws}."

        elif action == "move_window":
            ws = tokens.get("workspace") or "1"
            app = tokens.get("app")
            if app:
                success = self.hypr.move_window_to_workspace(ws, app_query=app)
                speech = f"Moved {app} to workspace {ws}."
            else:
                success = self.hypr.move_window_to_workspace(ws)
                speech = f"Moved window to workspace {ws}."

        elif action == "focus_direction":
            direction = tokens.get("direction") or "r"
            dir_code = {"left": "l", "right": "r", "up": "u", "down": "d"}.get(direction, direction)
            success = self.hypr.focus_direction(dir_code)
            speech = f"Focused {direction}."

        elif action == "focus_app":
            app = tokens.get("app") or text.replace("focus", "").strip()
            success = self.hypr.focus_window_by_class(app)
            speech = f"Focused {app}."

        elif action == "close_window":
            success = self.hypr.close_active_window()
            speech = "Closed window."

        elif action == "toggle_fullscreen":
            success = self.hypr.toggle_fullscreen()
            speech = "Toggled fullscreen."

        elif action == "toggle_floating":
            success = self.hypr.toggle_floating()
            speech = "Toggled floating."

        elif action == "toggle_scratchpad":
            success = self.hypr.toggle_special_workspace("scratchpad")
            speech = "Toggled scratchpad."

        return {
            "domain": "window_manager",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
