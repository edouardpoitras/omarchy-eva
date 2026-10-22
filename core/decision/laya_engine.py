"""Laya Decision Engine Adapter.

Wraps the legacy ModernBERT ONNX decision classifier into the BaseDecisionEngine interface.
"""

from typing import Any, Dict, List, Optional

from core.decision.base import BaseDecisionEngine, DecisionQuestion, DecisionResult
from core.system1_laya import LayaDecisionEngine


class LayaDecisionEngineAdapter(BaseDecisionEngine):
    """Adapter allowing the ONNX ModernBERT Laya classifier to be used pluggably."""

    def __init__(self, laya: Optional[LayaDecisionEngine] = None):
        super().__init__(model_name="laya-modernbert", is_local_only=True)
        self.laya = laya or LayaDecisionEngine()

    def predict(
        self,
        state: str,
        questions: Dict[str, DecisionQuestion],
        images: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, DecisionResult]:
        res_laya = self.laya.predict(state)
        intent = res_laya.get("intent", "UNKNOWN")
        conf = float(res_laya.get("confidence", 0.0))
        dist = res_laya.get("distribution", {})

        results: Dict[str, DecisionResult] = {}
        for q_id, q in questions.items():
            results[q_id] = DecisionResult(
                question_id=q_id,
                selected_option=intent,
                confidence=conf,
                probabilities=dist,
                latency_ms=res_laya.get("latency_ms", 0.0),
                metadata={"engine": "laya", "available": res_laya.get("available", False)},
            )
        return results
