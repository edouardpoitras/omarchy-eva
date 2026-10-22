"""Decision Model Registry for managing and swapping pluggable local decision engines."""

from typing import Dict, List, Optional

from core.decision.base import BaseDecisionEngine
from core.decision.clef_engine import ClefDecisionEngine


class DecisionModelRegistry:
    """Registry maintaining available local decision engines."""

    def __init__(self):
        self._engines: Dict[str, BaseDecisionEngine] = {}
        self._active_engine_name: str = "clef-flash"

        # Register default local engines
        self.register("clef-flash", ClefDecisionEngine(model_name="clef-flash"))
        self.register("clef", ClefDecisionEngine(model_name="clef"))

    def register(self, name: str, engine: BaseDecisionEngine):
        """Register a decision engine."""
        self._engines[name.lower()] = engine

    def _ensure_engine(self, name: str):
        key = name.lower()
        if key in self._engines:
            return
        if key == "laya":
            try:
                from core.decision.laya_engine import LayaDecisionEngineAdapter
                self.register("laya", LayaDecisionEngineAdapter())
            except Exception:
                pass

    def get(self, name: Optional[str] = None) -> BaseDecisionEngine:
        """Retrieve the requested or active decision engine."""
        key = (name or self._active_engine_name).lower()
        self._ensure_engine(key)
        if key in self._engines:
            return self._engines[key]
        # Fallback to clef-flash
        return self._engines.get("clef-flash", list(self._engines.values())[0])

    def set_active_engine(self, name: str) -> bool:
        """Switch the globally active decision engine."""
        key = name.lower()
        if key in self.list_engines():
            self._active_engine_name = key
            return True
        return False

    def get_active_engine_name(self) -> str:
        return self._active_engine_name

    def list_engines(self) -> List[str]:
        engines = list(self._engines.keys())
        if "laya" not in engines:
            engines.append("laya")
        return engines


# Singleton instance
decision_registry = DecisionModelRegistry()
