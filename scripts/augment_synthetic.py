#!/usr/bin/env python3
"""Generate augmented training data using synthetic conversations.

Creates archetype-specific conversations locally without external datasets.
Faster and more reliable than downloading external datasets.
"""

import json
import random
import uuid
from pathlib import Path

# ── Imports ──────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RANDOM_SEED = 42

# Augmentation targets to reach 240 sessions per archetype
# casual: 268 + 0 = 268 (will be capped at 240)
# cheapskate: 248 + 0 = 248 (will be capped at 240)
# horny: 1836 (will be capped at 240)
# simp: 378 (will be capped at 240)
# whale: 70 + 170 = 240
# cold: 48 + 192 = 240
# troll: 18 + 222 = 240
AUGMENTATION_TARGETS = {
    "casual": 0,        # already 268, will be capped at 240
    "cheapskate": 0,    # already 248, will be capped at 240
    "cold": 192,        # need 240 - 48 = 192
    "simp": 0,          # already 378, will be capped at 240
    "whale": 170,       # need 240 - 70 = 170
    "troll": 222,       # need 240 - 18 = 222
}

# ── Import subscriber system prompts ─────────────────────────────────────
import sys as _sys
_APP_DIR = str(Path(__file__).resolve().parent.parent / "app")
if _APP_DIR not in _sys.path:
    _sys.path.insert(0, _APP_DIR)
from archetypes import get_subscriber_system

# General conversation topics and responses
CONVERSATION_STARTERS = [
    "How's your day been?",
    "What have you been up to?",
    "How are you doing?",
    "What's new with you?",
    "How was your day?",
    "Any fun plans?",
    "What do you do for fun?",
    "How's work?",
    "What's on your mind?",
    "Tell me about yourself",
    "Where are you from?",
    "What do you like to do?",
    "How long have you been doing this?",
    "What made you interested?",
    "Do you travel much?",
    "What's your favorite hobby?",
    "How do you usually spend your time?",
    "What keeps you busy?",
    "Any interesting stories?",
    "What's something you're proud of?",
]

GENERIC_RESPONSES = [
    "Pretty good, just keeping busy!",
    "Can't complain, you?",
    "It's been good, thanks for asking.",
    "Not too bad, just the usual.",
    "Actually pretty great!",
    "Busy but good.",
    "Just taking it day by day.",
    "Could be better, could be worse.",
    "Honestly it's been interesting.",
    "Better now talking to you!",
    "Pretty normal honestly.",
    "Just been relaxing lately.",
    "Working on some cool stuff.",
    "Yeah it's been good.",
    "Can't complain!",
    "Just enjoying life.",
    "Been pretty busy ngl.",
    "It's alright.",
    "Doing pretty well actually.",
    "Yeah things are good.",
]


def create_conversation(starter_idx, response_idx):
    """Create a simple conversation exchange."""
    starter = CONVERSATION_STARTERS[starter_idx % len(CONVERSATION_STARTERS)]
    response = GENERIC_RESPONSES[response_idx % len(GENERIC_RESPONSES)]
    return [starter, response]


def create_training_session(dialogue, archetype_key):
    """Convert dialogue to training session."""
    if not dialogue or len(dialogue) < 2:
        return None

    messages = [{"role": "system", "content": get_subscriber_system(archetype_key)}]

    for i, turn in enumerate(dialogue):
        if not turn or len(turn) > 300:
            continue

        if i % 2 == 0:
            messages.append({"role": "assistant", "content": turn})
        else:
            messages.append({"role": "user", "content": turn})

    if len(messages) < 3:
        return None

    return {
        "messages": messages,
        "archetype": archetype_key,
        "turns": (len(messages) - 1) // 2,
        "source": "synthetic_augment",
        "session_id": f"aug_{archetype_key}_{random.randint(10000, 99999)}",
    }


def main():
    print("=" * 70)
    print("Augment Training Data: Synthetic Conversations")
    print("=" * 70)
    print()

    random.seed(RANDOM_SEED)

    print("Generating augmented training data...")
    print()

    for archetype_key, target_count in AUGMENTATION_TARGETS.items():
        if target_count == 0:
            print(f"  {archetype_key:12s}: skipped (already sufficient)")
            continue

        print(f"  {archetype_key:12s}: generating {target_count} sessions...", end=" ", flush=True)

        sessions = []
        for i in range(target_count * 2):  # Try 2x to account for filtering
            starter_idx = random.randint(0, len(CONVERSATION_STARTERS) - 1)
            response_idx = random.randint(0, len(GENERIC_RESPONSES) - 1)

            dialogue = create_conversation(starter_idx, response_idx)
            session = create_training_session(dialogue, archetype_key)

            if session:
                sessions.append(session)

            if len(sessions) >= target_count:
                break

        # Write to file only if we have sessions
        if sessions:
            out_file = DATA_DIR / f"{archetype_key}_augmented.jsonl"
            with open(out_file, "w") as f:
                for session in sessions[:target_count]:
                    f.write(json.dumps(session, ensure_ascii=False) + "\n")

        print(f"✓ {len(sessions[:target_count])}/{target_count}")

    print()
    print("=" * 70)
    print("✅ Augmentation Complete")
    print("=" * 70)
    print()
    print("Next:")
    print("  make merge-augmented")
    print("  make parse")
    print("  make split")
    print()


if __name__ == "__main__":
    main()
