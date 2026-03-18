#!/usr/bin/env python3
"""Augment training data using daily_dialog dataset.

Downloads daily_dialog conversations and formats them as training data
for underrepresented archetypes. This runs locally without GPU.
"""

import json
import random
from pathlib import Path
from collections import defaultdict

try:
    from datasets import load_dataset
except ImportError:
    print("ERROR: datasets library not found. Install with: pip install datasets")
    exit(1)

# ── Imports ──────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RANDOM_SEED = 42

# Augmentation targets (conversations to generate per archetype)
AUGMENTATION_TARGETS = {
    "casual": 75,
    "cheapskate": 40,
    "cold": 85,
    "simp": 0,
    "whale": 80,
    "troll": 80,
    # horny: skip (already capped at 500)
}

# ── Import subscriber system prompts ─────────────────────────────────────
import sys as _sys
_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in _sys.path:
    _sys.path.insert(0, _APP_DIR)
from archetypes import get_subscriber_system


def format_conversation_as_training(dialogue, archetype_key):
    """Convert a dialogue into a training session with archetype system prompt."""
    if len(dialogue) < 2:
        return None

    # Treat even turns as subscriber (assistant), odd turns as Jasmin (user)
    messages = [{"role": "system", "content": get_subscriber_system(archetype_key)}]

    for i, turn in enumerate(dialogue):
        if not turn or len(turn) > 300:  # Skip empty or very long turns
            continue

        if i % 2 == 0:
            # Subscriber (assistant)
            messages.append({"role": "assistant", "content": turn})
        else:
            # Jasmin (user)
            messages.append({"role": "user", "content": turn})

    # Need at least system + 1 exchange (4 messages total)
    if len(messages) < 3:
        return None

    return {
        "messages": messages,
        "archetype": archetype_key,
        "turns": (len(messages) - 1) // 2,  # Count of exchanges
        "source": "daily_dialog_augment",
        "session_id": f"aug_{archetype_key}_{random.randint(10000, 99999)}",
    }


def main():
    print("=" * 70)
    print("Augment Training Data: Using Conversational Dataset")
    print("=" * 70)
    print()

    # Try multiple conversational datasets
    dataset = None
    datasets_to_try = [
        ("blended_skill_talk", "train"),
        ("conv_ai_2", "train"),
        ("empathetic_dialogues", "train"),
    ]

    for dataset_name, split in datasets_to_try:
        print(f"Trying {dataset_name}...")
        try:
            dataset = load_dataset(dataset_name, split=split)
            print(f"✓ Loaded {dataset_name}")
            break
        except Exception as e:
            print(f"  ✗ {dataset_name}: {str(e)[:80]}")

    if dataset is None:
        print()
        print("ERROR: Could not load any conversational dataset")
        print()
        print("Install datasets: pip install datasets>=2.14.0")
        exit(1)

    print(f"✓ Loaded {len(dataset)} items")
    print()

    # Filter and prepare dialogues (handle different dataset formats)
    print("Filtering and preparing dialogues...")
    dialogues = []
    for i, item in enumerate(dataset):
        dialogue = None

        # Try different field names for dialogue
        if "utterances" in item:
            # blended_skill_talk, empathetic_dialogues format
            utterances = item.get("utterances", [])
            if isinstance(utterances, list) and utterances:
                dialogue = [u.get("utterance", u) if isinstance(u, dict) else u for u in utterances]
        elif "dialog" in item:
            # daily_dialog format (if available)
            dialogue = item.get("dialog", [])
        elif "dialogue" in item:
            dialogue = item.get("dialogue", [])
        elif "context" in item and "response" in item:
            # Conv_ai_2 format - combine context + response
            context = item.get("context", "").split(" __eou__ ")
            response = item.get("response", "")
            if context and response:
                dialogue = context + [response]

        if isinstance(dialogue, list) and 2 <= len(dialogue) <= 12:
            # Filter out empty/None turns
            dialogue = [t for t in dialogue if t and isinstance(t, str) and len(t.strip()) > 0]
            if 2 <= len(dialogue) <= 12:
                dialogues.append(dialogue)

        if (i + 1) % 5000 == 0:
            print(f"  Processed {i + 1}/{len(dataset)}...")

    print(f"✓ Filtered to {len(dialogues)} valid dialogues (2-12 turns)")
    print()

    # Shuffle
    random.seed(RANDOM_SEED)
    random.shuffle(dialogues)

    # Generate augmented data per archetype
    print("Generating augmented training data...")
    print()

    archetype_sessions = defaultdict(list)
    dialogue_idx = 0

    for archetype_key, target_count in AUGMENTATION_TARGETS.items():
        if target_count == 0:
            print(f"  {archetype_key:12s}: skipped (already sufficient)")
            continue

        print(f"  {archetype_key:12s}: generating {target_count} sessions...", end=" ", flush=True)
        sessions = []
        attempts = 0
        max_attempts = target_count * 10  # Try up to 10x to find valid dialogues

        while len(sessions) < target_count and dialogue_idx < len(dialogues) and attempts < max_attempts:
            dialogue = dialogues[(dialogue_idx + attempts) % len(dialogues)]
            session = format_conversation_as_training(dialogue, archetype_key)
            if session:
                sessions.append(session)
            attempts += 1

        archetype_sessions[archetype_key] = sessions
        print(f"✓ {len(sessions)}/{target_count}")
        dialogue_idx += max_attempts

    print()

    # Write per-archetype JSONL files
    print("Writing augmented data files...")
    for archetype_key, sessions in archetype_sessions.items():
        if not sessions:
            continue

        out_file = DATA_DIR / f"{archetype_key}_augmented.jsonl"
        with open(out_file, "w") as f:
            for session in sessions:
                f.write(json.dumps(session, ensure_ascii=False) + "\n")

        print(f"  {archetype_key:12s}: {len(sessions):3d} sessions → {out_file.name}")

    print()
    print("=" * 70)
    print("✅ Augmentation Complete")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Review the augmented data:")
    print("     head data/casual_augmented.jsonl")
    print()
    print("  2. Merge augmented data with original:")
    print("     make merge-augmented")
    print()
    print("  3. Re-parse and split:")
    print("     make parse && make split")
    print()


if __name__ == "__main__":
    main()
