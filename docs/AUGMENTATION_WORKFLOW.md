# Augmentation Workflow: Local + Colab

This document describes how to augment training data with archetype-specific general conversations.

## Step 1: Local — Create General Conversation Templates

On your M1 Mac:

```bash
make augment
```

This creates ~75 general conversation starter `.txt` files in `chat_data/general_100.txt` through `general_174.txt`.

**Output:**
- `chat_data/general_100.txt` — `chat_data/general_174.txt` (75 files)
- Each file: 2 turns (conversation starter + generic response)
- Format: timestamps + content (matches `parse_chats.py` expectations)

## Step 2: Upload to Google Drive

Upload your entire `chat_data/` directory to Google Drive:

```
/content/drive/MyDrive/subscriber-sim/chat_data/
```

Make sure it includes:
- Original chat files (`1.txt`, `2.txt`, etc.)
- Augmented general conversations (`general_100.txt` → `general_174.txt`)

## Step 3: Colab — Generate Archetype-Specific Responses

In your Colab notebook, **add a new cell before training (before Cell 5)** with this code:

```python
# Mount Drive (if not already mounted)
from google.colab import drive
drive.mount('/content/drive')

# Load the augmentation script
augment_script = open('/content/drive/MyDrive/subscriber-sim/scripts/colab_augment_generate.py').read()
exec(augment_script)
```

This cell will:
1. Load the ~75 general conversation templates from `chat_data/`
2. Use the base model to generate 3 archetype-specific versions for each:
   - **Casual** — friendly, warm, conversational
   - **Simp** — emotionally attached, asking about creator's life
   - **Horny** — flirty and sexual, even in general chat
3. Save augmented conversations back to `chat_data/` with archetype-specific prefixes:
   - `casual_200.txt` → `casual_274.txt`
   - `simp_200.txt` → `simp_274.txt`
   - `horny_200.txt` → `horny_274.txt`

**⏱️ Runtime:** ~10-15 minutes on Colab GPU (generates 75 conversations × 3 archetypes = 225 augmented files)

## Step 4: Parse & Split

After augmentation runs, in the Colab notebook run:

```bash
!cd /content/drive/MyDrive/subscriber-sim && make parse
!cd /content/drive/MyDrive/subscriber-sim && make split
```

This will:
1. **Parse ALL chat files** in `chat_data/` (original + augmented) into per-archetype JSONL
   - `data/horny.jsonl` — now includes augmented horny conversations
   - `data/casual.jsonl` — includes augmented casual conversations
   - `data/simp.jsonl` — includes augmented simp conversations
   - Other archetypes unchanged
2. **Balance archetypes** and create train/valid split
   - Cap horny at 500 (was 1,836)
   - Casual now has original + ~75 augmented = more training diversity
   - Result: `data/mlx/train.jsonl` + `data/mlx/valid.jsonl`

## Step 5: Train

Run the training cell (Cell 5) as normal. The model now trains on:
- ✅ Original OnlyFans chat data
- ✅ ~225 augmented general conversations with archetype-specific responses
- ✅ Strong role declaration system prompts (fixing role confusion)
- ✅ Balanced archetype distribution

## Expected Improvements

**Before:**
- Model memorizes OnlyFans patterns
- Sometimes responds as Jasmin instead of subscriber
- Horny dominates (50% of data)

**After:**
- ✅ Model learns archetype boundaries (what IS vs ISN'T casual/simp/horny)
- ✅ Better role clarity (trained with "YOU ARE the subscriber..." prompt)
- ✅ Can handle general conversation naturally within archetype
- ✅ Better balanced (horny is now 27% of training data)
- ✅ Less memorization (diverse conversation patterns)

## Troubleshooting

**Q: Augmentation cell runs very slowly in Colab**
A: This is normal—generating 225 responses with inference takes time. Can run multiple cells in parallel if needed.

**Q: "AttributeError: module 'app.archetypes' has no attribute..."**
A: Make sure the `sys.path` insert in the cell points to the correct location. Check that `/content/drive/MyDrive/subscriber-sim/app/archetypes.py` exists.

**Q: Parse fails after augmentation**
A: Make sure all `.txt` files in `chat_data/` follow the format:
```
HH:MM am/pm
turn content
HH:MM am/pm
turn content
```

**Q: Train/valid split is imbalanced**
A: This is expected with small augmented datasets. The sanity check will warn if any archetype has < 5 valid samples. This is fine for small datasets.
