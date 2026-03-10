"""
Modal GPU compute — Jasmin inference.

Deploy once:
    modal deploy scripts/modal_server.py

The Streamlit app calls this directly via Modal client (no HTTP server needed).
"""

from pathlib import Path
from threading import Thread

import modal

app  = modal.App("jasmin-inference")

ADAPTER_DIR = Path(__file__).parent.parent / "models" / "adapter"

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04",
        add_python="3.11",
    )
    .pip_install(
        "torch>=2.4.0",
        "transformers>=4.40.0",
        "peft>=0.10.0",
        "accelerate>=0.27.0",
        "bitsandbytes>=0.43.0",
        "safetensors>=0.4.0",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
    .add_local_dir(ADAPTER_DIR, remote_path="/adapter")
)

volume = modal.Volume.from_name("jasmin-model-cache", create_if_missing=True)
MODEL_CACHE = "/cache"
BASE_MODEL  = "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"


@app.cls(
    image=image,
    gpu="L4",
    volumes={MODEL_CACHE: volume},
    scaledown_window=60,
    timeout=120,
)
class JasminModel:

    @modal.enter()
    def load(self):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

        print("Loading tokenizer…")
        self.tokenizer = AutoTokenizer.from_pretrained(
            BASE_MODEL, cache_dir=MODEL_CACHE
        )
        self.tokenizer.pad_token = self.tokenizer.eos_token

        print("Loading 4-bit base model…")
        base = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto",
            cache_dir=MODEL_CACHE,
        )

        print("Applying LoRA adapter…")
        self.model = PeftModel.from_pretrained(base, "/adapter")
        self.model.eval()
        print("✅ Ready")

    @modal.method()
    def generate(self, messages: list[dict], stop: list[str], max_tokens: int,
                 temperature: float, top_p: float, rep_pen: float):
        """Yields response tokens — call with .remote_gen() from the client."""
        from transformers import TextIteratorStreamer

        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)

        # Short replies: skip thread+streamer overhead, generate synchronously
        if max_tokens <= 70:
            import torch
            with torch.inference_mode():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    repetition_penalty=rep_pen,
                    do_sample=temperature > 0,
                    pad_token_id=self.tokenizer.eos_token_id,
                )
            new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            text_out = self.tokenizer.decode(new_ids, skip_special_tokens=True)
            for s in stop:
                if s in text_out:
                    text_out = text_out[:text_out.index(s)]
            yield text_out
            return

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        Thread(
            target=self.model.generate,
            kwargs=dict(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=rep_pen,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
                streamer=streamer,
            ),
            daemon=True,
        ).start()

        buf = ""
        for token in streamer:
            buf += token
            for s in stop:
                if s in buf:
                    yield buf[:buf.index(s)]
                    return
            yield buf
            buf = ""
