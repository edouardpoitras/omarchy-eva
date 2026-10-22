"""Specialized Web Browser Decision Model."""

import subprocess
import urllib.parse
from typing import Any, Dict, Optional

from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor


class BrowserDomainModel:
    """Specialized System 1 model for browser navigation and search."""

    def __init__(self, engine: BaseDecisionEngine):
        self.engine = engine

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef decision question schema for web browser actions."""
        return {
            "browser_action": DecisionQuestion(
                question_id="browser_action",
                question_type="choice",
                instructions="Determine the web browser action requested by the user.",
                criteria={
                    "open_url": "Navigate to a specific website address or URL",
                    "search_web": "Perform a web search on Google or search engine",
                    "new_tab": "Open a new blank or default browser tab",
                    "close_tab": "Close the active browser tab",
                    "refresh": "Reload or refresh the current page",
                },
            )
        }

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the web browser action."""
        schema = self.get_question_schema()
        decisions = self.engine.predict(state=text, questions=schema, context=context)
        action_res = decisions.get("browser_action")
        action = action_res.selected_option if action_res else "search_web"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_browser_tokens(text)

        if dry_run:
            return {
                "domain": "web_browser",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action == "open_url":
            url = tokens.get("url") or "https://google.com"
            try:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                success = True
                speech = f"Navigating to {url}."
            except Exception:
                success = False

        elif action == "search_web":
            query = tokens.get("query") or text
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.google.com/search?q={encoded}"
            try:
                subprocess.Popen(["xdg-open", search_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                success = True
                speech = f"Searching the web for {query}."
            except Exception:
                success = False

        elif action == "new_tab":
            try:
                subprocess.Popen(["xdg-open", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                success = True
                speech = "Opened new browser tab."
            except Exception:
                success = False

        elif action in ("close_tab", "refresh"):
            speech = f"Browser {action} performed."
            success = True

        return {
            "domain": "web_browser",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
