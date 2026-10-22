"""Specialized Terminal and CLI Execution Decision Model."""

import os
import shlex
import subprocess
from typing import Any, Dict, Optional

from core.app_indexer import AppIndexer
from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor


class TerminalDomainModel:
    """Specialized System 1 model for terminal and shell execution."""

    def __init__(self, engine: BaseDecisionEngine, apps: Optional[AppIndexer] = None):
        self.engine = engine
        self.apps = apps or AppIndexer()

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef decision question schema for terminal operations."""
        return {
            "terminal_action": DecisionQuestion(
                question_id="terminal_action",
                question_type="choice",
                instructions="Determine the terminal action requested by the user.",
                criteria={
                    "open_terminal": "Launch or focus a new or existing terminal window (ghostty, kitty, alacritty)",
                    "run_command": "Execute a specific command, shell script, or tool in the terminal",
                    "clear_terminal": "Clear the terminal screen",
                },
            )
        }

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the terminal action."""
        schema = self.get_question_schema()
        decisions = self.engine.predict(state=text, questions=schema, context=context)
        action_res = decisions.get("terminal_action")
        action = action_res.selected_option if action_res else "open_terminal"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_terminal_tokens(text)

        if dry_run:
            return {
                "domain": "terminal",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action == "open_terminal":
            # Preferred terminals
            for term in ["ghostty", "foot", "alacritty", "kitty"]:
                if self.apps.find_app(term):
                    success = self.apps.launch_app(term)
                    speech = f"Opened {term}."
                    break
            if not success:
                try:
                    subprocess.Popen(["x-terminal-emulator"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    success = True
                    speech = "Opened terminal."
                except Exception:
                    success = False

        elif action == "run_command":
            cmd = tokens.get("command") or text
            try:
                # Launch inside terminal or run directly
                subprocess.Popen(
                    ["ghostty", "-e", "bash", "-c", f"{cmd}; exec bash"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                success = True
                speech = f"Running {cmd} in terminal."
            except Exception:
                try:
                    subprocess.Popen(shlex.split(cmd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                    success = True
                    speech = f"Executed {cmd}."
                except Exception:
                    success = False

        elif action == "clear_terminal":
            speech = "Cleared terminal."
            success = True

        return {
            "domain": "terminal",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
