"""
Convert a HuggingFace PEFT LoRA adapter (from Unsloth training) to MLX format
so it can be loaded by mlx_lm.server.

Usage:
    python scripts/convert_adapter_to_mlx.py \
        --input  models/finetuned \
        --output models/finetuned-mlx

What this does:
    PEFT key:  base_model.model.model.layers.0.self_attn.q_proj.lora_A.weight
    MLX key:   model.layers.0.self_attn.q_proj.lora_a

    PEFT lora_A.weight shape: (r, in_features)  → MLX lora_a shape: (in_features, r)  [transposed]
    PEFT lora_B.weight shape: (out_features, r) → MLX lora_b shape: (r, out_features) [transposed]
"""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from safetensors import safe_open
from safetensors.numpy import save_file as save_safetensors


def peft_to_mlx_key(peft_key: str) -> str:
    """Convert a PEFT adapter key to its MLX equivalent."""
    k = peft_key

    # Remove Unsloth/PEFT wrapper prefix
    if k.startswith("base_model.model."):
        k = k[len("base_model.model."):]

    # Remove .weight suffix (MLX stores arrays directly, not as module weights)
    if k.endswith(".weight"):
        k = k[:-len(".weight")]

    # Lowercase A/B to match MLX convention
    k = k.replace(".lora_A", ".lora_a").replace(".lora_B", ".lora_b")

    return k


def convert(input_dir: Path, output_dir: Path) -> None:
    adapter_file = input_dir / "adapter_model.safetensors"
    if not adapter_file.exists():
        raise FileNotFoundError(f"No adapter_model.safetensors found in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading {adapter_file} …")
    mlx_weights: dict[str, np.ndarray] = {}

    with safe_open(str(adapter_file), framework="numpy") as f:
        keys = list(f.keys())
        print(f"  Found {len(keys)} tensors")

        for peft_key in keys:
            tensor = f.get_tensor(peft_key)  # numpy array, already float32
            mlx_key = peft_to_mlx_key(peft_key)

            # PEFT stores lora_A as (r, in_features) and lora_B as (out_features, r).
            # MLX expects lora_a as (in_features, r) and lora_b as (r, out_features).
            # Both need a transpose.
            if ".lora_a" in mlx_key or ".lora_b" in mlx_key:
                tensor = tensor.T

            mlx_weights[mlx_key] = tensor
            print(f"  {peft_key}")
            print(f"    → {mlx_key}  shape {tensor.shape}")

    out_st = output_dir / "adapters.safetensors"
    save_safetensors(mlx_weights, str(out_st))
    print(f"\n✅  Saved {len(mlx_weights)} tensors → {out_st}")

    # Derive num_layers from the converted keys (max layer index + 1)
    layer_indices = set()
    for k in mlx_weights:
        parts = k.split(".")
        if len(parts) > 2 and parts[1] == "layers" and parts[2].isdigit():
            layer_indices.add(int(parts[2]))
    num_layers = max(layer_indices) + 1 if layer_indices else 32
    print(f"✅  Detected {num_layers} LoRA-covered layers")

    # Copy tokenizer files needed by mlx_lm
    for fname in ["tokenizer.json", "tokenizer_config.json", "chat_template.jinja"]:
        src = input_dir / fname
        if src.exists():
            shutil.copy(src, output_dir / fname)
            print(f"✅  Copied {fname}")

    # Write MLX adapter config (always overwrite — not the PEFT format)
    mlx_config_path = output_dir / "adapter_config.json"
    if mlx_config_path.exists():
        with open(input_dir / "adapter_config.json") as f:
            peft_cfg = json.load(f)
        mlx_cfg = {
            "num_layers": num_layers,
            "lora_parameters": {
                "rank": peft_cfg.get("r", 16),
                "alpha": peft_cfg.get("lora_alpha", 16),
                "dropout": peft_cfg.get("lora_dropout", 0.0),
                "scale": peft_cfg.get("lora_alpha", 16) / peft_cfg.get("r", 16),
            },
            "linear_layers": peft_cfg.get("target_modules", []),
        }
        with open(output_dir / "adapter_config.json", "w") as f:
            json.dump(mlx_cfg, f, indent=2)
        print("✅  Wrote MLX adapter_config.json")

    print(f"\nDone! MLX adapter is ready at: {output_dir}")
    print("Start the server with:")
    print(f"  mlx_lm.server --model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit \\")
    print(f"                --adapter-path {output_dir} --port 8080")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert PEFT LoRA adapter → MLX format")
    parser.add_argument("--input",  default="models/finetuned",     help="Path to PEFT adapter directory")
    parser.add_argument("--output", default="models/finetuned-mlx", help="Output path for MLX adapter")
    args = parser.parse_args()

    convert(Path(args.input), Path(args.output))


if __name__ == "__main__":
    main()
