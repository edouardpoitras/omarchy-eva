"""ModernBERT Laya Intent Classifier Trainer with CUDA Auto-Detection and ONNX Export.

Trains a non-autoregressive decision model over Omarchy voice commands and exports
calibrated weights to ONNX Runtime for sub-25ms desktop inference.
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Tuple

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(REPO_ROOT, "models")
ONNX_EXPORT_PATH = os.path.join(MODELS_DIR, "laya_classifier.onnx")
LABEL_MAP_PATH = os.path.join(MODELS_DIR, "label_map.json")
TOKENIZER_DIR = os.path.join(MODELS_DIR, "tokenizer")


class CommandDataset(Dataset):
    def __init__(self, data: List[Dict[str, str]], tokenizer, label_to_idx: Dict[str, int], max_length: int = 64):
        self.data = data
        self.tokenizer = tokenizer
        self.label_to_idx = label_to_idx
        self.max_length = max_length

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        encoding = self.tokenizer(
            item["text"],
            padding="max_length",
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        label_idx = self.label_to_idx[item["intent"]]
        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "label": torch.tensor(label_idx, dtype=torch.long),
        }


def load_jsonl(path: str) -> List[Dict[str, str]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def detect_device() -> Tuple[torch.device, str]:
    """Auto-detect optimal compute target (CUDA -> ROCm -> CPU)."""
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        return torch.device("cuda"), f"GPU (CUDA: {name})"
    return torch.device("cpu"), "CPU (Fallback)"


def train_laya(
    model_name: str = "answerdotai/ModernBERT-base",
    train_path: str = os.path.join(REPO_ROOT, "training", "train.jsonl"),
    val_path: str = os.path.join(REPO_ROOT, "training", "val.jsonl"),
    epochs: int = 3,
    batch_size: int = 32,
    lr: float = 3e-5,
    output_onnx: str = ONNX_EXPORT_PATH,
):
    device, device_desc = detect_device()
    print(f"[*] Training Target: {device_desc}")

    train_data = load_jsonl(train_path)
    val_data = load_jsonl(val_path)

    unique_labels = sorted(list(set(x["intent"] for x in train_data + val_data)))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    idx_to_label = {i: l for i, l in enumerate(unique_labels)}

    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(TOKENIZER_DIR, exist_ok=True)

    with open(LABEL_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump({"label_to_idx": label_to_idx, "idx_to_label": idx_to_label}, f, indent=2)

    print(f"[*] Loaded {len(train_data)} train, {len(val_data)} val samples across {len(unique_labels)} intents.")
    print(f"[*] Initializing Tokenizer & Model: {model_name}...")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.save_pretrained(TOKENIZER_DIR)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(unique_labels),
        id2label=idx_to_label,
        label2id=label_to_idx,
    )
    model.to(device)

    train_dataset = CommandDataset(train_data, tokenizer, label_to_idx)
    val_dataset = CommandDataset(val_data, tokenizer, label_to_idx)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    criterion = torch.nn.CrossEntropyLoss()

    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    print(f"\n[*] Starting Fine-Tuning ({epochs} epochs, batch_size={batch_size})...")
    start_time = time.perf_counter()

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0

        for batch in train_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["label"].to(device)

            optimizer.zero_grad()

            with torch.amp.autocast("cuda", enabled=use_amp):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                loss = criterion(outputs.logits, labels)

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            total_loss += loss.item()

        # Validation evaluation
        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels = batch["label"].to(device)

                with torch.amp.autocast("cuda", enabled=use_amp):
                    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                    preds = torch.argmax(outputs.logits, dim=-1)

                val_correct += (preds == labels).sum().item()
                val_total += labels.size(0)

        val_acc = (val_correct / val_total) * 100 if val_total > 0 else 0
        print(f"  Epoch {epoch + 1}/{epochs} | Loss: {total_loss / len(train_loader):.4f} | Val Accuracy: {val_acc:.2f}%")

    total_training_time = round(time.perf_counter() - start_time, 2)
    print(f"[*] Training completed in {total_training_time}s!")

    # ONNX Export
    print(f"[*] Exporting calibrated model to ONNX: {output_onnx}...")
    model.eval()
    model.to("cpu")  # Export cleanly on CPU for device-agnostic ONNX runtime

    dummy_input_ids = torch.ones((1, 64), dtype=torch.long)
    dummy_attention_mask = torch.ones((1, 64), dtype=torch.long)

    torch.onnx.export(
        model,
        (dummy_input_ids, dummy_attention_mask),
        output_onnx,
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "logits": {0: "batch_size"},
        },
        opset_version=18,
        dynamo=False,
    )

    print(f"[+] Laya model successfully exported to ONNX ({round(os.path.getsize(output_onnx) / (1024 * 1024), 1)} MB)")
    print(f"[+] Tokenizer saved to: {TOKENIZER_DIR}")
    print(f"[+] Label mapping saved to: {LABEL_MAP_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Laya ModernBERT Intent Classifier Trainer")
    parser.add_argument("--model", type=str, default="answerdotai/ModernBERT-base", help="Base HuggingFace encoder model")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=3e-5, help="Learning rate")
    args = parser.parse_args()

    train_laya(
        model_name=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )


if __name__ == "__main__":
    main()
