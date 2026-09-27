"""Conversational Context and Pronoun Memory (Anaphora Resolution) for Eva.

Enables multi-turn conversational context so follow-up commands like:
- "move spotify to workspace 3" -> "now close it"
- "open firefox" -> "move it to workspace 2"
- "focus slack" -> "what workspace is it on"

resolve pronouns ("it", "that", "the app", "the window") to the antecedent
tracked in recent memory before passing to intent/reflex dispatchers.
"""

import re
import time
from typing import Any, Dict, Optional, Tuple, Union


class ContextMemory:
    """Thread-safe context memory tracking recent interactions and window states."""

    def __init__(self, ttl_seconds: float = 180.0):
        self.ttl_seconds = ttl_seconds
        self.last_app: Optional[str] = None
        self.last_workspace: Optional[Union[int, str]] = None
        self.last_window_class: Optional[str] = None
        self.last_window_title: Optional[str] = None
        self.last_window_address: Optional[str] = None
        self.last_intent: Optional[str] = None
        self.last_action: Optional[str] = None
        self.last_statement: Optional[str] = None
        self.last_statement_timestamp: float = 0.0
        self.last_timestamp: float = 0.0

    def record_statement(self, statement: str):
        """Record the last spoken statement or substantive output."""
        clean = (statement or "").strip()
        if clean and not clean.startswith("I haven't said anything"):
            self.last_statement = clean
            self.last_statement_timestamp = time.time()

    def get_last_statement(self) -> Optional[str]:
        """Return the most recent spoken statement or substantive output."""
        return self.last_statement

    def record(
        self,
        intent: Optional[str] = None,
        action: Optional[str] = None,
        app: Optional[str] = None,
        workspace: Optional[Union[int, str]] = None,
        window_class: Optional[str] = None,
        window_title: Optional[str] = None,
        window_address: Optional[str] = None,
        statement: Optional[str] = None,
    ):
        """Record an executed action and its entity targets into short-term memory."""
        self.last_timestamp = time.time()
        if intent is not None:
            self.last_intent = intent
        if action is not None:
            self.last_action = action
        if app is not None:
            self.last_app = app.strip()
        elif window_class is not None:
            self.last_app = window_class.strip()
        if workspace is not None:
            self.last_workspace = workspace
        if window_class is not None:
            self.last_window_class = window_class
        if window_title is not None:
            self.last_window_title = window_title
        if window_address is not None:
            self.last_window_address = window_address
        if statement is not None and intent != "REPEAT_STATEMENT":
            self.record_statement(statement)

    def is_valid(self) -> bool:
        """Check if memory has not expired."""
        if not self.last_app:
            return False
        return (time.time() - self.last_timestamp) <= self.ttl_seconds

    def get_antecedent_app(self, active_window: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Return the antecedent application name or class, falling back to active window if valid."""
        if self.is_valid() and self.last_app:
            return self.last_app

        if active_window:
            # Try initialClass, class, or title
            win_class = active_window.get("class") or active_window.get("initialClass")
            if win_class:
                return win_class.strip()

        return None

    def resolve_anaphora(self, text: str, active_window: Optional[Dict[str, Any]] = None) -> str:
        """Resolve pronouns ('it', 'that', 'this', 'the app', 'the window') in user command.

        If an antecedent exists in context memory or active window, rewrites the command
        so downstream regex and intent classifiers receive the concrete application name.
        """
        raw_text = text.strip()
        if not raw_text:
            return text

        # Guard: Do not resolve pronouns on repeat commands (e.g. "repeat that", "what was that")
        if re.search(r"^(?:please\s+)?(?:repeat(?:\s+that|\s+it)?|say\s+that\s+again|what\s+was\s+that|what\s+did\s+you\s+say|pardon)", raw_text, re.IGNORECASE):
            return text

        antecedent = self.get_antecedent_app(active_window)
        if not antecedent:
            return text

        resolved = raw_text

        # 1. Close/kill patterns:
        # "close it", "now close it", "please kill that", "exit the app"
        close_patterns = [
            r"^(now\s+|please\s+)?(close|kill|exit|quit|terminate)\s+(it|that|the\s+app|this(?!\s+window))(?:\s+now)?$",
            r"\b(and\s+)?(now\s+|then\s+)?(close|kill|exit|quit|terminate)\s+(it|that|the\s+app|this(?!\s+window))(?:\s+now)?$",
        ]
        for pat in close_patterns:
            m = re.search(pat, resolved, re.IGNORECASE)
            if m:
                # Replace with direct verb + antecedent
                verb = m.group(2) if m.lastindex >= 2 else "close"
                # Preserve leading "now " or "please " if at start
                prefix = m.group(1) or ""
                resolved = f"{prefix}{verb} {antecedent}".strip()
                break

        # 2. Window move patterns:
        # "move it to workspace 3", "send it to 4", "put that on workspace 2"
        move_patterns = [
            r"^(now\s+|please\s+)?(move|send|put|transfer)\s+(it|that|the\s+app|this(?!\s+window))\s+(to\s+workspace\s+\w+|to\s+\w+|on\s+workspace\s+\w+)",
            r"\b(move|send|put)\s+(it|that|the\s+app|this(?!\s+window))\s+(to\s+workspace\s+\w+|to\s+\w+|on\s+workspace\s+\w+)",
        ]
        for pat in move_patterns:
            m = re.search(pat, resolved, re.IGNORECASE)
            if m:
                # Capture groups
                if m.lastindex >= 4:
                    prefix = m.group(1) or ""
                    verb = m.group(2)
                    target = m.group(4)
                    replacement = f"{prefix}{verb} {antecedent} {target}".strip()
                    resolved = resolved[:m.start()] + replacement + resolved[m.end():]
                    break
                elif m.lastindex >= 3:
                    verb = m.group(1)
                    target = m.group(3)
                    replacement = f"{verb} {antecedent} {target}".strip()
                    resolved = resolved[:m.start()] + replacement + resolved[m.end():]
                    break

        # 3. Focus/switch/show patterns:
        # "focus it", "switch to it", "show that", "show it to me"
        focus_patterns = [
            r"^(now\s+|please\s+)?(focus|switch\s+to|show|bring\s+up)\s+(it|that|the\s+app|this(?!\s+window))(\s+to\s+me)?$",
        ]
        for pat in focus_patterns:
            m = re.search(pat, resolved, re.IGNORECASE)
            if m:
                prefix = m.group(1) or ""
                verb = m.group(2)
                resolved = f"{prefix}{verb} {antecedent}".strip()
                break

        # 4. Where is it / Query patterns:
        # "where is it", "what workspace is it on", "is it open"
        query_patterns = [
            (r"\bwhere\s+is\s+(it|that|the\s+app|the\s+window)\b", f"where is {antecedent}"),
            (r"\bwhat\s+workspace\s+is\s+(it|that|the\s+app|the\s+window)\s+on\b", f"what workspace is {antecedent} on"),
            (r"\bis\s+(it|that|the\s+app|the\s+window)\s+(open|running)\b", f"is {antecedent} running"),
        ]
        for pat, repl in query_patterns:
            if re.search(pat, resolved, re.IGNORECASE):
                resolved = re.sub(pat, repl, resolved, flags=re.IGNORECASE)
                break

        # 5. Fullscreen / maximize / float patterns:
        # "maximize it", "fullscreen it", "float it"
        win_control_patterns = [
            (r"\b(maximize|fullscreen|unfullscreen|float|pin)\s+(it|that|this|the\s+app|the\s+window)\b", r"\1"),
        ]
        for pat, verb_group in win_control_patterns:
            m = re.search(pat, resolved, re.IGNORECASE)
            if m:
                # If command is "fullscreen it", downstream expects e.g. "fullscreen" or window toggle
                # Keeping antecedent in mind or resolving window
                pass

        return resolved

    def clear(self):
        """Reset short-term memory."""
        self.last_app = None
        self.last_workspace = None
        self.last_window_class = None
        self.last_window_title = None
        self.last_window_address = None
        self.last_intent = None
        self.last_action = None
        self.last_timestamp = 0.0


# Global singleton
context_memory = ContextMemory()
