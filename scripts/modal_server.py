"""
Modal GPU compute — Jasmin inference.

Deploy once:
    modal volume put jasmin-model models/adapter/ /adapter/
    modal deploy scripts/modal_server.py

The Streamlit app calls this directly via Modal client (no HTTP server needed).
"""

from threading import Thread

import modal

app = modal.App("jasmin-inference")

BASE_MODEL = "unsloth/meta-llama-3.1-8b-instruct-bnb-4bit"

# Modal Volume — upload adapter once with:
#   modal volume put jasmin-model models/lora-adapter /
model_volume = modal.Volume.from_name("jasmin-model", create_if_missing=True)
VOLUME_MOUNT = "/root/adapter"
ADAPTER_PATH = "/root/adapter/lora-adapter"

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04",
        add_python="3.11",
    )
    .pip_install(
        "torch>=2.4.0",
        "transformers>=4.40.0,<5.0.0",
        "tokenizers>=0.19.0,<0.21.0",
        "accelerate>=0.27.0",
        "bitsandbytes>=0.43.0",
        "safetensors>=0.4.0",
        "sentencepiece>=0.2.0",
        "peft>=0.10.0",
        extra_index_url="https://download.pytorch.org/whl/cu124",
    )
)


@app.cls(
    image=image,
    gpu="L4",
    volumes={VOLUME_MOUNT: model_volume},
    scaledown_window=60,
    timeout=120,
)
class JasminModel:

    @modal.enter()
    def load(self):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig, PreTrainedTokenizerFast

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

        print("Loading tokenizer…")
        self.tokenizer = PreTrainedTokenizerFast(
            tokenizer_file=f"{ADAPTER_PATH}/tokenizer.json",
            bos_token="<|begin_of_text|>",
            eos_token="<|eot_id|>",
            pad_token="<|eot_id|>",
        )
        with open(f"{ADAPTER_PATH}/chat_template.jinja") as f:
            self.tokenizer.chat_template = f.read()

        print("Loading base model…")
        base = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto",
        )

        print("Applying LoRA adapter…")
        self.model = PeftModel.from_pretrained(base, ADAPTER_PATH)
        self.model.eval()
        print("✅ Ready")

    @modal.method()
    def generate(self, messages: list[dict], stop: list[str], max_tokens: int,
                 temperature: float, top_p: float, rep_pen: float,
                 prefill: str = ""):
        """Yields response tokens — call with .remote_gen() from the client."""
        from transformers import TextIteratorStreamer

        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        if prefill:
            text += prefill
        inputs = {k: v for k, v in self.tokenizer(text, return_tensors="pt").items()
                  if k != "token_type_ids"}
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

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
            # Strip prefill if model regenerated it
            if prefill and text_out.startswith(prefill):
                text_out = text_out[len(prefill):]
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
        prefill_stripped = False
        for token in streamer:
            buf += token
            # Strip prefill if model regenerated it (only check once at start)
            if prefill and not prefill_stripped and buf.startswith(prefill):
                buf = buf[len(prefill):]
                prefill_stripped = True
            for s in stop:
                if s in buf:
                    yield buf[:buf.index(s)]
                    return
            yield buf
            buf = ""
