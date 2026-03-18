#!/usr/bin/env python3
"""Merge augmented data with original per-archetype JSONL files."""

import json
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main():
    print("=" * 70)
    print("Merge Augmented Data with Original")
    print("=" * 70)
    print()

    archetypes = ["casual", "cheapskate", "cold", "simp", "whale", "troll", "horny"]
    merged_counts = defaultdict(int)

    for archetype in archetypes:
        original_file = DATA_DIR / f"{archetype}.jsonl"
        augmented_file = DATA_DIR / f"{archetype}_augmented.jsonl"

        if not original_file.exists():
            print(f"  {archetype:12s}: original file not found, skipping")
            continue

        # Load original
        original_sessions = []
        with open(original_file, "r") as f:
            for line in f:
                if line.strip():
                    original_sessions.append(json.loads(line))

        # Load augmented (if exists)
        augmented_sessions = []
        if augmented_file.exists():
            with open(augmented_file, "r") as f:
                for line in f:
                    if line.strip():
                        augmented_sessions.append(json.loads(line))

        # Merge
        total_before = len(original_sessions)
        original_sessions.extend(augmented_sessions)
        total_after = len(original_sessions)

        # Write merged back to original file
        with open(original_file, "w") as f:
            for session in original_sessions:
                f.write(json.dumps(session, ensure_ascii=False) + "\n")

        added = total_after - total_before
        if added > 0:
            print(f"  {archetype:12s}: {total_before:4d} → {total_after:4d} (+{added})")
        else:
            print(f"  {archetype:12s}: {total_before:4d} (no augmented data)")

        merged_counts[archetype] = total_after

    print()
    print("=" * 70)
    print("✅ Merge Complete")
    print("=" * 70)
    print()

    # Summary
    total_before = sum(merged_counts.values())
    print("Summary after merge:")
    for arch in archetypes:
        count = merged_counts[arch]
        if count > 0:
            print(f"  {arch:12s}: {count:4d} sessions")

    print()
    print(f"Total: {total_before} sessions")
    print()
    print("Next: make parse && make split")
    print()


if __name__ == "__main__":
    main()
