"""
COLAB CELL: Generate archetype-specific augmented training data.

Run this cell in Colab AFTER uploading chat_data/ with augmented .txt files.
It uses the base model to generate casual, simp, and horny responses to
general conversations, creating high-quality archetype-specific training data.

Paste this entire script into a Colab cell and run it.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# ── Setup ────────────────────────────────────────────────────────────────
# Assumes subscriber_sim/ is mounted at /content/drive/MyDrive/subscriber-sim
REPO_DIR = Path("/content/drive/MyDrive/subscriber-sim")
CHAT_DIR = REPO_DIR / "chat_data"
DATA_DIR = REPO_DIR / "data"

# Add app/ to path for imports
sys.path.insert(0, str(REPO_DIR / "app"))
from archetypes import get_subscriber_system

# ── Configuration ────────────────────────────────────────────────────────
# Strategic augmentation to balance archetype distribution
# Target: horny=27%, simp=20%, casual=18%, cheapskate=15%, whale=8%, cold=7%, troll=5%
# Current: horny=33%, simp=25%, casual=18%, cheapskate=16%, whale=5%, cold=3%, troll=1%
AUGMENTATION_CONFIG = {
    "troll": {"count": 80, "weight": 1.0},      # 18 → 98 (boost 5.4x)
    "whale": {"count": 80, "weight": 1.0},      # 70 → 150 (boost 2.1x)
    "cold": {"count": 85, "weight": 1.0},       # 48 → 133 (boost 2.8x)
    "casual": {"count": 75, "weight": 1.0},     # 268 → 343 (boost 1.3x)
    "cheapskate": {"count": 40, "weight": 1.0}, # 248 → 288 (boost 1.2x)
    "simp": {"count": 0, "weight": 1.0},        # 378 → 378 (already large)
    # "horny": skip (500 capped, already dominant)
}
ARCHETYPES_TO_AUGMENT = list(AUGMENTATION_CONFIG.keys())
MAX_DIALOGUES = 500  # Process first 500 augmented dialogues
SEED = 42

# ── Archetype-specific inference parameters ────────────────────────────
ARCHETYPE_CONFIG = {
    "casual": {
        "temp": 0.70,
        "max_tokens": 60,
    },
    "simp": {
        "temp": 0.80,
        "max_tokens": 80,
    },
    "cheapskate": {
        "temp": 0.75,
        "max_tokens": 70,
    },
    "whale": {
        "temp": 0.75,
        "max_tokens": 70,
    },
    "troll": {
        "temp": 0.80,
        "max_tokens": 60,
    },
    "cold": {
        "temp": 0.60,
        "max_tokens": 40,
    },
}


def parse_txt_file(filepath):
    """Parse a .txt chat file into list of turns."""
    content = filepath.read_text()
    lines = content.strip().split("\n")

    turns = []
    current_turn = []

    for line in lines:
        if re.match(r"^\d{1,2}:\d{2}\s*(am|pm)$", line, re.IGNORECASE):
            # Timestamp marks turn boundary
            if current_turn:
                turns.append("\n".join(current_turn).strip())
                current_turn = []
        elif line.strip():
            current_turn.append(line.strip())

    if current_turn:
        turns.append("\n".join(current_turn).strip())

    return turns


def generate_archetype_response(model, tokenizer, user_turn, archetype_key):
    """Generate a single turn response for the given archetype."""
    system_prompt = get_subscriber_system(archetype_key)
    config = ARCHETYPE_CONFIG[archetype_key]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_turn},
    ]

    # Apply chat template
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    # Generate
    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=config["max_tokens"],
            temperature=config["temp"],
            top_p=0.9,
            do_sample=True,
            repetition_penalty=1.15,
        )

    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
    ).strip()

    return response


def create_augmented_conversation(dialogue_turns, archetype_key, model, tokenizer):
    """Create an augmented conversation for a specific archetype.

    Takes alternating general conversation turns and generates archetype-specific responses.
    Returns a list of (turn, response) pairs formatted as .txt file lines.
    """
    lines = []
    timestamp_hour = 9
    timestamp_min = 30

    # Alternate between parsing dialogue turns and generating responses
    for i, user_turn in enumerate(dialogue_turns):
        # Add timestamp
        am_pm = "am" if timestamp_hour < 12 else "pm"
        timestamp = f"{timestamp_hour % 12:02d}:{timestamp_min:02d} {am_pm}"
        lines.append(timestamp)

        if i % 2 == 0:
            # User (Jasmin) speaks - use dialogue turn as-is
            lines.append(user_turn)
        else:
            # Subscriber speaks - generate archetype response
            response = generate_archetype_response(
                model, tokenizer, user_turn, archetype_key
            )
            lines.append(response)

        # Increment timestamp
        timestamp_min += 30
        if timestamp_min == 60:
            timestamp_min = 0
            timestamp_hour += 1

    return lines


def main():
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM

    print("=" * 70)
    print("Colab: Generate Archetype-Specific Augmented Data")
    print("=" * 70)
    print()

    # Load model
    print("Loading base model...")
    model_name = "meta-llama/Llama-2-7b-chat-hf"  # or use 8B if available in Colab
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name, torch_dtype=torch.float16, device_map="auto"
    )
    print(f"✓ Loaded {model_name}")
    print()

    # Find augmented .txt files
    augmented_files = sorted(CHAT_DIR.glob("general_*.txt"))[:MAX_DIALOGUES]
    print(f"Found {len(augmented_files)} general conversation files")
    print()
    print("Augmentation plan (to balance distribution):")
    for arch, config in AUGMENTATION_CONFIG.items():
        print(f"  {arch:12s}: generate {config['count']} files (weight: {config['weight']:.1f}x)")
    print()

    # Process each general dialogue
    total_written = {arch: 0 for arch in ARCHETYPES_TO_AUGMENT}
    file_counter = {arch: 200 for arch in ARCHETYPES_TO_AUGMENT}  # Start at 200 to avoid collisions

    for file_idx, filepath in enumerate(augmented_files):
        dialogue_turns = parse_txt_file(filepath)

        if len(dialogue_turns) < 3:
            continue

        # Generate archetype-specific versions (only up to count limit per archetype)
        for archetype_key in ARCHETYPES_TO_AUGMENT:
            config = AUGMENTATION_CONFIG[archetype_key]

            # Skip if we've reached the target count for this archetype
            if total_written[archetype_key] >= config["count"]:
                continue

            print(f"[{file_idx + 1}/{len(augmented_files)}] {archetype_key:12s}...", end=" ", flush=True)

            lines = create_augmented_conversation(dialogue_turns, archetype_key, model, tokenizer)

            # Write as .txt file
            output_file = CHAT_DIR / f"{archetype_key}_{file_counter[archetype_key]}.txt"
            output_file.write_text("\n".join(lines) + "\n")
            total_written[archetype_key] += 1
            file_counter[archetype_key] += 1
            print("✓")

    print()
    print("=" * 70)
    print("✅ Done — Strategic augmentation complete")
    print("=" * 70)
    total_augmented = 0
    for arch in ARCHETYPES_TO_AUGMENT:
        count = total_written[arch]
        target = AUGMENTATION_CONFIG[arch]["count"]
        total_augmented += count
        status = "✓" if count >= target else f"({count}/{target})"
        print(f"  {arch:12s}: {count:3d} files written {status}")
    print()
    print(f"Total augmented: {total_augmented} files")
    print()
    print("Next steps (back in local terminal):")
    print("  1. Run: make parse")
    print("  2. Run: make split")
    print("  3. Training with balanced distribution!")
    print()


if __name__ == "__main__":
    main()
