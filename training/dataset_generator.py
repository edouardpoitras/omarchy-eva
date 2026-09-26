"""Dataset Generator for Laya Decision Model Fine-Tuning.

Generates training and validation splits from schema.yaml using:
1. Combinatorial slot substitution and conversational jitter (prefixes, suffixes, filler words).
2. Synthetic variation expansion via Omarchy Agent CLI (`omarchy agent prompt`).
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from typing import Any, Dict, List, Tuple

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(REPO_ROOT, "training", "schema.yaml")
OUTPUT_DIR = os.path.join(REPO_ROOT, "training")

# Conversational jitter prefixes and suffixes mimicking natural human speech
PREFIXES = [
    "",
    "please ",
    "hey eva ",
    "eva ",
    "could you ",
    "can you ",
    "quick ",
    "go ahead and ",
    "i want to ",
    "um ",
    "uh ",
]

SUFFIXES = [
    "",
    " please",
    " for me",
    " now",
    " right now",
    " thanks",
]


def load_schema(path: str = SCHEMA_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def expand_templates_rule_based(intent: str, data: dict, count_per_intent: int = 150) -> List[str]:
    """Generate diverse variations by combining slots, jitter, and phonetic phrasing."""
    templates = data.get("templates", [])
    slots = data.get("slots", {})

    generated = set()

    for tmpl in templates:
        # Check if template has slots
        slot_names = re.findall(r"\{([a-zA-Z0-9_]+)\}", tmpl)
        if not slot_names:
            for p in PREFIXES:
                for s in SUFFIXES:
                    generated.add(f"{p}{tmpl}{s}".strip())
        else:
            # Substitute each slot value
            for s_name in slot_names:
                values = slots.get(s_name, [])
                for val in values:
                    subbed = tmpl.replace(f"{{{s_name}}}", str(val))
                    for p in PREFIXES:
                        for s in SUFFIXES:
                            generated.add(f"{p}{subbed}{s}".strip())

    items = list(generated)
    random.shuffle(items)
    return items[:count_per_intent]


def expand_via_agent_cli(intent: str, desc: str, seed_samples: List[str], target_count: int = 50) -> List[str]:
    """Call Omarchy's default coding agent to generate natural speech variations."""
    prompt = f"""Generate {target_count} realistic spoken voice command variations for the following Linux desktop intent.
Intent: {intent}
Description: {desc}
Seed examples:
{json.dumps(seed_samples[:5])}

Requirements:
- Simulate spoken English utterances (include occasional filler words like 'um', 'please', 'hey eva', casual phrasing).
- Return ONLY a raw JSON array of strings, nothing else. No markdown, no commentary.
Format: ["utterance 1", "utterance 2", ...]"""

    try:
        res = subprocess.run(
            ["omarchy", "agent", "prompt", "--inline", prompt],
            capture_output=True,
            text=True,
            timeout=30.0,
            check=False,
        )
        if res.returncode == 0:
            out = res.stdout.strip()
            # Extract JSON array
            m = re.search(r"\[.*\]", out, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, list):
                    return [str(x).strip().lower() for x in parsed if isinstance(x, str)]
    except Exception as e:
        print(f"Warning: Agent expansion failed: {e}, falling back to rule-based generation.")

    return []


def build_dataset(
    count_per_intent: int = 150,
    use_agent: bool = False,
    val_split: float = 0.2,
    output_dir: str = OUTPUT_DIR,
) -> Tuple[str, str]:
    """Build full balanced dataset split into train.jsonl and val.jsonl."""
    schema = load_schema()
    intents = schema.get("intents", {})

    all_data = []

    print(f"Generating dataset across {len(intents)} intent categories...")

    for intent, info in intents.items():
        desc = info.get("description", "")
        samples = expand_templates_rule_based(intent, info, count_per_intent)

        if use_agent:
            print(f"  Synthesizing AI variations for {intent} via Omarchy Agent...")
            agent_samples = expand_via_agent_cli(intent, desc, samples, target_count=40)
            samples = list(set(samples + agent_samples))

        for text in samples:
            all_data.append({"text": text, "intent": intent})

        print(f"  [+] {intent}: {len(samples)} samples generated")

    random.shuffle(all_data)

    # Train / Val Split
    split_idx = int(len(all_data) * (1 - val_split))
    train_data = all_data[:split_idx]
    val_data = all_data[split_idx:]

    train_path = os.path.join(output_dir, "train.jsonl")
    val_path = os.path.join(output_dir, "val.jsonl")

    with open(train_path, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for item in val_data:
            f.write(json.dumps(item) + "\n")

    print(f"\nDataset generation complete!")
    print(f"  Total samples: {len(all_data)}")
    print(f"  Training set:   {len(train_data)} samples -> {train_path}")
    print(f"  Validation set: {len(val_data)} samples -> {val_path}")

    return train_path, val_path


def main():
    parser = argparse.ArgumentParser(description="Omarchy Eva Dataset Generator")
    parser.add_argument("--count", type=int, default=120, help="Target samples per intent")
    parser.add_argument("--use-agent", action="store_true", help="Use Omarchy Agent CLI for AI synthesis")
    parser.add_argument("--val-split", type=float, default=0.2, help="Validation split fraction")
    args = parser.parse_args()

    build_dataset(
        count_per_intent=args.count,
        use_agent=args.use_agent,
        val_split=args.val_split,
    )


if __name__ == "__main__":
    main()
