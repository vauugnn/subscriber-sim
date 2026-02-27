# Subscriber Sim

LoRA fine-tuning pipeline that trains a Jasmin chatbot from real OnlyFans chat data.

## What It Does

1. **Data Collection** — A Gradio chat UI where you type as Jasmin while the model plays different subscriber archetypes (horny, cheapskate, casual, troll, whale, cold, simp). Sessions are saved to Google Drive as JSONL.
2. **Fine-Tuning** — LoRA adapter training on Llama 3.1 8B (4-bit) using parsed chat data + collected sessions. Runs on Colab with Unsloth + SFTTrainer.
3. **Inference** — The fine-tuned Jasmin model responds autonomously to real subscribers.

## Notebook Cells

| Cell | Purpose |
|------|---------|
| 0 | Colab bootstrap — install deps, restart kernel |
| 1 | Imports + Google Drive mount |
| 2 | Load Llama 3.1 8B via Unsloth (`TRAINING_MODE` flag) |
| 3 | Subscriber archetype definitions (7 types) |
| 4 | Subscriber bot logic + session save/export |
| 5 | Gradio subscriber sim (data collection mode) |
| 6 | LoRA adapter setup (r=16, targets q/k/v/o/gate/up/down) |
| 7 | Load & format training data from `sessions.jsonl` |
| 8 | SFTTrainer — 3 epochs, batch=2, grad_accum=4, lr=2e-4 |
| 9 | Inference test with sample prompts |
| 10 | Subscriber sim (post-training, keep collecting data) |

## Training Flow

```
Set TRAINING_MODE = True → Run Cells 0-4, 6-9 → Fine-tune
Set TRAINING_MODE = False → Run Cells 0-5 or 10 → Collect data / chat
```

## Data

- `data/sessions.jsonl` — 256 pre-parsed sessions (8,496 turns) from real chat exports
- Additional sessions saved via the Gradio UI go to Google Drive

### Role Mapping

In the Gradio UI, you type as Jasmin (`user`) and the model responds as a subscriber (`assistant`). When saving to JSONL for training, roles are **flipped** so the model learns to be Jasmin:

| Gradio | Saved JSONL | Who |
|--------|-------------|-----|
| user | assistant | Jasmin (you) |
| assistant | user | Subscriber (model) |

## Stack

- [Unsloth](https://github.com/unslothai/unsloth) — 4-bit model loading + LoRA
- [trl](https://github.com/huggingface/trl) — SFTTrainer
- [Gradio](https://gradio.app) — Chat UI
- Google Colab — GPU runtime + Drive storage
