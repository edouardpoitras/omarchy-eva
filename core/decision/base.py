"""Base interfaces and data structures for pluggable decision models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional, Union


@dataclass
class DecisionQuestion:
    """Represents a structured question defined in the decision schema."""

    question_id: str
    question_type: str = "choice"  # 'choice', 'bool' (or 'noul'), 'score'
    instructions: str = ""
    criteria: Union[Dict[str, str], List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert question to standard Clef JSON schema representation."""
        return {
            "type": "noul" if self.question_type in ("bool", "boolean", "noul") else self.question_type,
            "instructions": self.instructions,
            "criteria": self.criteria,
        }


@dataclass
class DecisionResult:
    """Standardized decision outcome for a question in the schema."""

    question_id: str
    selected_option: str
    confidence: float
    probabilities: Dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "selected_option": self.selected_option,
            "confidence": round(self.confidence, 4),
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "latency_ms": round(self.latency_ms, 2),
            "metadata": self.metadata,
        }


class BaseDecisionEngine(ABC):
    """Abstract interface for pluggable local decision engines (Clef, Laya, etc.)."""

    def __init__(self, model_name: str = "base", is_local_only: bool = True):
        self.model_name = model_name
        self.is_local_only = is_local_only

    @abstractmethod
    def predict(
        self,
        state: str,
        questions: Dict[str, DecisionQuestion],
        images: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, DecisionResult]:
        """Process an input state and schema of questions, returning probabilities and choices.

        Args:
            state: The text representation of the current state (input + history + desktop context).
            questions: Dictionary mapping question_id to DecisionQuestion.
            images: Optional list of local image file paths for multimodal inspection (e.g. screenshot).
            context: Additional structured desktop/environment metadata.

        Returns:
            Dictionary mapping question_id to DecisionResult.
        """
        raise NotImplementedError
