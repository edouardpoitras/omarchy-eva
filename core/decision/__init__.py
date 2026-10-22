"""Hierarchical System 1 Decision Architecture for Eva.

Provides pluggable local decision models, domain routing, and token extraction.
"""

from core.decision.base import BaseDecisionEngine, DecisionQuestion, DecisionResult
from core.decision.clef_engine import ClefDecisionEngine
from core.decision.registry import decision_registry

__all__ = [
    "BaseDecisionEngine",
    "DecisionQuestion",
    "DecisionResult",
    "ClefDecisionEngine",
    "decision_registry",
]
