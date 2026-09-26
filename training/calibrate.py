"""Temperature Scaling & Epistemic Calibration for Laya Decisions.

Computes Expected Calibration Error (ECE) and fits temperature parameter T
against strictly proper scoring rules so probabilities mathematically reflect accuracy.
"""

import argparse
import json
import os
from typing import Dict, List, Tuple

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(REPO_ROOT, "models")
ONNX_PATH = os.path.join(MODELS_DIR, "laya_classifier.onnx")
TOKENIZER_DIR = os.path.join(MODELS_DIR, "tokenizer")
LABEL_MAP_PATH = os.path.join(MODELS_DIR, "label_map.json")
CALIBRATION_PATH = os.path.join(MODELS_DIR, "calibration.json")
VAL_DATA_PATH = os.path.join(REPO_ROOT, "training", "val.jsonl")


def softmax(x: np.ndarray, temp: float = 1.0) -> np.ndarray:
    e_x = np.exp((x - np.max(x, axis=-1, keepdims=True)) / temp)
    return e_x / np.sum(e_x, axis=-1, keepdims=True)


def compute_ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 10) -> float:
    """Compute Expected Calibration Error (ECE)."""
    confidences = np.max(probs, axis=1)
    predictions = np.argmax(probs, axis=1)
    accuracies = predictions == labels

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
        prop_in_bin = np.mean(in_bin)

        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(accuracies[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin

    return float(ece)


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """Optimize temperature scalar T to minimize Negative Log-Likelihood (Platt scaling)."""
    best_t = 1.0
    best_nll = float("inf")

    # Grid search over candidate temperatures
    for candidate_t in np.linspace(0.1, 5.0, 500):
        probs = softmax(logits, temp=candidate_t)
        # Avoid log(0)
        eps = 1e-12
        probs_clipped = np.clip(probs, eps, 1.0)
        nll = -np.mean(np.log(probs_clipped[np.arange(len(labels)), labels]))
        if nll < best_nll:
            best_nll = nll
            best_t = float(candidate_t)

    return round(best_t, 3)


def run_calibration(
    onnx_path: str = ONNX_PATH,
    val_path: str = VAL_DATA_PATH,
    tokenizer_dir: str = TOKENIZER_DIR,
    label_map_path: str = LABEL_MAP_PATH,
    output_path: str = CALIBRATION_PATH,
) -> Dict[str, any]:
    if not os.path.exists(onnx_path):
        raise FileNotFoundError(f"ONNX model not found at {onnx_path}. Run training first.")

    with open(label_map_path, "r", encoding="utf-8") as f:
        label_map = json.load(f)["label_to_idx"]

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir)
    session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])

    val_texts = []
    val_labels = []
    with open(val_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                val_texts.append(item["text"])
                val_labels.append(label_map[item["intent"]])

    val_labels = np.array(val_labels)

    print(f"[*] Running ONNX evaluation over {len(val_texts)} validation samples...")

    # Batch tokenization
    enc = tokenizer(val_texts, padding="max_length", truncation=True, max_length=64, return_tensors="np")
    ort_inputs = {
        "input_ids": enc["input_ids"].astype(np.int64),
        "attention_mask": enc["attention_mask"].astype(np.int64),
    }

    ort_outputs = session.run(None, ort_inputs)
    logits = ort_outputs[0]

    # Pre-calibration evaluation
    uncalibrated_probs = softmax(logits, temp=1.0)
    acc = float(np.mean(np.argmax(uncalibrated_probs, axis=1) == val_labels))
    ece_before = compute_ece(uncalibrated_probs, val_labels)

    # Temperature optimization
    optimal_t = fit_temperature(logits, val_labels)
    calibrated_probs = softmax(logits, temp=optimal_t)
    ece_after = compute_ece(calibrated_probs, val_labels)

    results = {
        "temperature": optimal_t,
        "accuracy": round(acc * 100, 2),
        "ece_before": round(ece_before, 4),
        "ece_after": round(ece_after, 4),
        "threshold": 0.85,
        "samples": len(val_texts),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n[+] Calibration Results:")
    print(f"    Accuracy:     {results['accuracy']}%")
    print(f"    Optimal Temp: {results['temperature']}")
    print(f"    ECE Before:   {results['ece_before']}")
    print(f"    ECE After:    {results['ece_after']} (lower is better)")
    print(f"[+] Saved to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Laya Temperature Calibration")
    parser.add_argument("--onnx", type=str, default=ONNX_PATH)
    parser.add_argument("--val-data", type=str, default=VAL_DATA_PATH)
    args = parser.parse_args()

    run_calibration(onnx_path=args.onnx, val_path=args.val_data)


if __name__ == "__main__":
    main()
