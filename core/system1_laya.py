"""Laya Non-Autoregressive Decision Engine (ONNX Runtime).

Executes sub-25ms typed intent classification with temperature-calibrated probabilities
over incoming user voice commands.
"""

import json
import os
import time
from typing import Any, Dict, Optional

try:
    import numpy as np
except ImportError:
    np = None

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(REPO_ROOT, "models")
ONNX_PATH = os.path.join(MODELS_DIR, "laya_classifier.onnx")
TOKENIZER_DIR = os.path.join(MODELS_DIR, "tokenizer")
LABEL_MAP_PATH = os.path.join(MODELS_DIR, "label_map.json")
CALIBRATION_PATH = os.path.join(MODELS_DIR, "calibration.json")


def softmax(x, temp: float = 1.0):
    if np is None:
        return x
    e_x = np.exp((x - np.max(x, axis=-1, keepdims=True)) / temp)
    return e_x / np.sum(e_x, axis=-1, keepdims=True)


class LayaDecisionEngine:
    """Non-autoregressive System 1 decision engine based on ModernBERT encoder ONNX."""

    def __init__(
        self,
        onnx_path: str = ONNX_PATH,
        tokenizer_dir: str = TOKENIZER_DIR,
        label_map_path: str = LABEL_MAP_PATH,
        calibration_path: str = CALIBRATION_PATH,
    ):
        self.onnx_path = onnx_path
        self.tokenizer_dir = tokenizer_dir
        self.label_map_path = label_map_path
        self.calibration_path = calibration_path

        self.session = None
        self.tokenizer = None
        self.idx_to_label = {}
        self.temperature = 1.0
        self.threshold = 0.85
        self.is_ready = False

        self._load_engine()

    def _load_engine(self):
        """Load ONNX session, tokenizer, label map, and calibration parameters."""
        if np is None or not (os.path.exists(self.onnx_path) and os.path.exists(self.label_map_path)):
            self.is_ready = False
            return

        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            # Load label mapping
            with open(self.label_map_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure integer keys
                self.idx_to_label = {int(k): v for k, v in data["idx_to_label"].items()}

            # Load calibration temperature
            if os.path.exists(self.calibration_path):
                with open(self.calibration_path, "r", encoding="utf-8") as f:
                    cal = json.load(f)
                    self.temperature = float(cal.get("temperature", 1.0))
                    self.threshold = float(cal.get("threshold", 0.85))

            # Initialize Tokenizer and ONNX session
            self.tokenizer = AutoTokenizer.from_pretrained(self.tokenizer_dir)

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            available = ort.get_available_providers()
            providers = [p for p in ["CUDAExecutionProvider", "CPUExecutionProvider"] if p in available] or ["CPUExecutionProvider"]
            self.session = ort.InferenceSession(self.onnx_path, sess_options=opts, providers=providers)
            self.is_ready = True
        except Exception as e:
            print(f"Warning: Laya model load failed: {e}. Falling back to reflex rules.")
            self.is_ready = False

    def predict(self, text: str) -> Dict[str, Any]:
        """Classify input text in a single forward pass, returning calibrated probabilities."""
        t_start = time.perf_counter()

        if not self.is_ready:
            return {
                "available": False,
                "intent": "UNKNOWN",
                "confidence": 0.0,
                "confident": False,
                "distribution": {},
                "latency_ms": round((time.perf_counter() - t_start) * 1000, 2),
            }

        # Tokenize (sub-1ms)
        enc = self.tokenizer(
            text,
            padding="max_length",
            truncation=True,
            max_length=64,
            return_tensors="np",
        )
        ort_inputs = {
            "input_ids": enc["input_ids"].astype(np.int64),
            "attention_mask": enc["attention_mask"].astype(np.int64),
        }

        # ONNX inference (~10-25ms)
        outputs = self.session.run(None, ort_inputs)
        logits = outputs[0][0]

        # Apply calibrated temperature scaling
        probs = softmax(logits, temp=self.temperature)

        top_idx = int(np.argmax(probs))
        top_intent = self.idx_to_label.get(top_idx, "UNKNOWN")
        top_confidence = float(probs[top_idx])

        distribution = {
            self.idx_to_label[i]: round(float(p), 4)
            for i, p in enumerate(probs)
            if i in self.idx_to_label
        }

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return {
            "available": True,
            "intent": top_intent,
            "confidence": round(top_confidence, 4),
            "confident": top_confidence >= self.threshold,
            "threshold": self.threshold,
            "temperature": self.temperature,
            "distribution": distribution,
            "latency_ms": latency_ms,
        }
