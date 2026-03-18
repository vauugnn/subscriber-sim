#!/usr/bin/env python3
"""Create synthetic general conversation templates for augmentation.

Creates basic conversational exchanges that can be augmented with
archetype-specific responses in Colab. This avoids daily_dialog
dataset script issues while providing good conversation starters.
"""

import random
from pathlib import Path

CHAT_DIR = Path(__file__).resolve().parent.parent / "chat_data"
OUTPUT_PREFIX = "general"
RANDOM_SEED = 42

# General conversation templates (one person asks, other responds generically)
CONVERSATION_STARTERS = [
    "How's your day been going?",
    "What have you been up to lately?",
    "How was your weekend?",
    "What's new with you?",
    "How are you doing today?",
    "What are you up to this evening?",
    "How's work been treating you?",
    "Any fun plans coming up?",
    "What do you like to do in your free time?",
    "How's the weather where you are?",
    "What's your favorite way to relax?",
    "Have you watched anything good lately?",
    "Do you have any hobbies?",
    "What's your favorite music?",
    "Are you more of an introvert or extrovert?",
    "What's something you learned recently?",
    "How do you usually spend your mornings?",
    "What's your favorite food?",
    "Do you travel much?",
    "What was the last movie you watched?",
    "How long have you been doing this?",
    "Where are you from?",
    "What made you interested in this?",
    "Do you have any pets?",
    "What's your go-to comfort food?",
]

GENERIC_RESPONSES = [
    "Pretty good, thanks for asking!",
    "Can't complain, just the usual.",
    "It's been good, busy but good.",
    "Not too bad, what about you?",
    "Same old same old, you know?",
    "Actually pretty great, glad you asked!",
    "Eh, it's been a day lol",
    "Better now, thanks!",
    "Pretty chill, just relaxing.",
    "Honestly I have no idea lol",
    "It's been interesting, that's for sure.",
    "Could be worse! How about you?",
    "Just taking it one day at a time.",
    "Pretty solid, can't complain.",
    "Living the dream! Just kidding, it's alright.",
]


def create_conversation(starter_idx, response_idx):
    """Create a simple conversation exchange."""
    starter = CONVERSATION_STARTERS[starter_idx % len(CONVERSATION_STARTERS)]
    response = GENERIC_RESPONSES[response_idx % len(GENERIC_RESPONSES)]

    lines = []
    hour = 9 + (starter_idx // 10) % 8
    min_start = 30 if (starter_idx % 2) == 0 else 0
    am_pm = "am" if hour < 12 else "pm"

    # First turn (starter)
    timestamp = f"{hour % 12:02d}:{min_start:02d} {am_pm}"
    lines.append(timestamp)
    lines.append(starter)

    # Second turn (response)
    min_response = 0 if min_start == 30 else 30
    if min_response == 0:
        hour += 1
    am_pm = "am" if hour < 12 else "pm"
    timestamp = f"{hour % 12:02d}:{min_response:02d} {am_pm}"
    lines.append(timestamp)
    lines.append(response)

    return "\n".join(lines)


def main():
    print("=" * 70)
    print("Create Augmentation Data: General conversation templates")
    print("=" * 70)
    print()

    CHAT_DIR.mkdir(parents=True, exist_ok=True)

    # Create conversation pairs
    random.seed(RANDOM_SEED)
    num_conversations = len(CONVERSATION_STARTERS) * 3  # 3x the number of starters

    file_num = 100
    for i in range(num_conversations):
        conversation = create_conversation(
            random.randint(0, len(CONVERSATION_STARTERS) - 1),
            random.randint(0, len(GENERIC_RESPONSES) - 1),
        )

        output_file = CHAT_DIR / f"{OUTPUT_PREFIX}_{file_num}.txt"
        output_file.write_text(conversation + "\n")
        file_num += 1

    print(f"✅ Created {num_conversations} general conversation .txt files")
    print(f"   Saved to: chat_data/general_100.txt → general_{file_num - 1}.txt")
    print()
    print("These will be augmented with archetype-specific responses in Colab.")
    print()
    print("Next steps:")
    print("  1. Upload chat_data/ to Google Drive")
    print("  2. In Colab notebook, run the colab_augment_generate cell")
    print("  3. Run: make parse && make split")
    print("  4. Train the model")
    print()


if __name__ == "__main__":
    main()
