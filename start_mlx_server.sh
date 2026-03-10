#!/usr/bin/env bash
# Start the MLX inference server natively on your Mac (Metal GPU).
# Run this BEFORE `docker compose up`.
# The Streamlit Docker container calls it at host.docker.internal:8080.
#
# NOTE: For deployment, use Modal instead — see scripts/modal_server.py
#
# Model:    mlx-community/Meta-Llama-3.1-8B-Instruct-4bit  (~4.5GB)
# Adapter:  models/finetuned-mlx/adapters.safetensors       (~160MB)

set -euo pipefail

cd "$(dirname "$0")"

BASE_MODEL="mlx-community/Meta-Llama-3.1-8B-Instruct-4bit"
PEFT_DIR="./models/finetuned"
MLX_ADAPTER="./models/finetuned-mlx"
PORT=8080
HOST="127.0.0.1"

echo "================================================"
echo " Jasmin MLX Inference Server"
echo "================================================"

# ── Convert PEFT adapter to MLX format (one-time) ────────────────────────────
if [ -d "$PEFT_DIR" ] && [ -f "$PEFT_DIR/adapter_model.safetensors" ]; then
    if [ ! -f "$MLX_ADAPTER/adapters.safetensors" ]; then
        echo "🔄  Converting PEFT adapter → MLX format (one-time setup)…"
        python3 scripts/convert_adapter_to_mlx.py \
            --input  "$PEFT_DIR" \
            --output "$MLX_ADAPTER"
        echo ""
    fi
fi

# ── Start the server ──────────────────────────────────────────────────────────
if [ -f "$MLX_ADAPTER/adapters.safetensors" ]; then
    echo "✅  Fine-tuned adapter: $MLX_ADAPTER"
    echo "    Base model:         $BASE_MODEL"
    echo "    Listening on:       $HOST:$PORT"
    echo "------------------------------------------------"
    mlx_lm.server \
        --model        "$BASE_MODEL" \
        --adapter-path "$MLX_ADAPTER" \
        --host         "$HOST" \
        --port         "$PORT"
else
    echo "ℹ️   No adapter found — starting base model only"
    echo "    Base model:   $BASE_MODEL"
    echo "    Listening on: $HOST:$PORT"
    echo "------------------------------------------------"
    mlx_lm.server \
        --model "$BASE_MODEL" \
        --host  "$HOST" \
        --port  "$PORT"
fi
