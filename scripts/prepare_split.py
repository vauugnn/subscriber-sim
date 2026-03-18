#!/usr/bin/env python3
"""Prepare balanced train/valid split from archetype-specific JSONL files.

Loads per-archetype data, applies caps to prevent over-representation,
mixes in general conversational data, then creates a balanced train/valid split.
"""

import json
import random
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MLX_DIR = DATA_DIR / "mlx"

# Archetype caps for balanced distribution (~14% each with 7 archetypes)
# Target: ~240 sessions per archetype → 1,680 total (90/10 split = 1,512 train, 168 valid)
ARCHETYPE_CAPS = {
    "horny": 240,           # was 1,836 → cap at 240
    "simp": 240,            # was 378 → cap at 240
    "casual": 240,          # was 343 (with augment) → cap at 240
    "cheapskate": 240,      # was 288 (with augment) → cap at 240
    "whale": 240,           # was 150 (with augment) → cap at 240
    "cold": 240,            # was 133 (with augment) → cap at 240
    "troll": 240,           # was 98 (with augment) → cap at 240
}

TRAIN_FRACTION = 0.90
RANDOM_SEED = 42


def load_jsonl(path):
    """Load JSONL file into list of dicts."""
    sessions = []
    if not path.exists():
        return sessions
    with open(path, "r") as f:
        for line in f:
            if line.strip():
                sessions.append(json.loads(line))
    return sessions


def write_jsonl(path, sessions):
    """Write list of dicts to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for session in sessions:
            f.write(json.dumps(session, ensure_ascii=False) + "\n")


def main():
    print("=" * 70)
    print("Prepare Train/Valid Split: Balance + Mix Archetypes")
    print("=" * 70)
    print()

    # Load per-archetype data
    print("Loading per-archetype data...")
    all_sessions = {arch: [] for arch in ARCHETYPE_CAPS}

    for archetype in ARCHETYPE_CAPS:
        archetype_file = DATA_DIR / f"{archetype}.jsonl"
        sessions = load_jsonl(archetype_file)
        print(f"  {archetype:12s}: {len(sessions):4d} sessions", end="")

        # Shuffle
        rng = random.Random(RANDOM_SEED)
        rng.shuffle(sessions)

        # Apply cap if set
        cap = ARCHETYPE_CAPS[archetype]
        if cap and len(sessions) > cap:
            sessions = sessions[:cap]
            print(f" → capped at {cap}")
        else:
            print()

        all_sessions[archetype] = sessions

    # Note: Augmented data is already mixed into per-archetype JSONL files
    # (via make merge-augmented which merges *_augmented.jsonl files)
    print()
    print("Augmented data status:")

    # Combine and shuffle
    print()
    print("Combining and balancing...")
    combined = []
    for archetype in ARCHETYPE_CAPS:
        combined.extend(all_sessions[archetype])

    rng = random.Random(RANDOM_SEED)
    rng.shuffle(combined)

    print(f"Total sessions: {len(combined)}")

    # Split
    split_idx = int(len(combined) * TRAIN_FRACTION)
    train_sessions = combined[:split_idx]
    valid_sessions = combined[split_idx:]

    print(f"Train: {len(train_sessions)} ({TRAIN_FRACTION * 100:.0f}%)")
    print(f"Valid: {len(valid_sessions)} ({(1 - TRAIN_FRACTION) * 100:.0f}%)")

    # Sanity check: verify system prompts are correct
    print()
    print("Sanity check: verifying system prompts...")
    if train_sessions:
        first_msg = train_sessions[0]["messages"][0]
        if first_msg["role"] != "system":
            print("  ⚠️  WARNING: First message is not system prompt!")
        if "YOU ARE the subscriber" not in first_msg["content"]:
            print("  ⚠️  WARNING: System prompt does NOT contain role declaration!")
            print("     Likely cause: run 'make parse' to regenerate with fixed prompts")
        else:
            print("  ✓ System prompts are correct (contains role declaration)")

    # Write split files
    print()
    print("Writing split files...")
    write_jsonl(DATA_DIR / "mlx" / "train.jsonl", train_sessions)
    write_jsonl(DATA_DIR / "mlx" / "valid.jsonl", valid_sessions)
    print("  ✓ data/mlx/train.jsonl written")
    print("  ✓ data/mlx/valid.jsonl written")

    # Statistics
    print()
    print("=" * 70)
    print("DISTRIBUTION: Train")
    print("=" * 70)
    train_counts = Counter(s["archetype"] for s in train_sessions)
    for arch in sorted(ARCHETYPE_CAPS.keys()):
        count = train_counts[arch]
        pct = (count / len(train_sessions) * 100) if train_sessions else 0
        print(f"  {arch:12s}: {count:4d} ({pct:5.1f}%)")

    print()
    print("=" * 70)
    print("DISTRIBUTION: Valid")
    print("=" * 70)
    valid_counts = Counter(s["archetype"] for s in valid_sessions)
    for arch in sorted(ARCHETYPE_CAPS.keys()):
        count = valid_counts[arch]
        pct = (count / len(valid_sessions) * 100) if valid_sessions else 0
        print(f"  {arch:12s}: {count:4d} ({pct:5.1f}%)")

    # Warn if any archetype has too few valid samples
    print()
    min_valid_samples = 5
    underrep = [arch for arch, count in valid_counts.items() if count < min_valid_samples]
    if underrep:
        print(f"⚠️  WARNING: These archetypes have < {min_valid_samples} valid samples:")
        for arch in underrep:
            print(f"    {arch}: {valid_counts[arch]}")

    print()
    print("=" * 70)
    print(f"✅ Done — Ready to train!")
    print("=" * 70)


if __name__ == "__main__":
    main()
