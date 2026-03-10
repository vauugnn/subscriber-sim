import os
import threading
from collections.abc import Generator

from archetypes import get_jasmin_system, get_jasmin_opening_system

# ── Backend selection ─────────────────────────────────────────────────────────
# Set INFERENCE_BACKEND=modal to use Modal GPU client.
# Set INFERENCE_BACKEND=adapter to use the local LoRA adapter (models/adapter).
# Default is "mlx" (local MLX server via HTTP).
BACKEND = os.getenv("INFERENCE_BACKEND", "mlx")

# MLX HTTP server settings (used when BACKEND=mlx)
MLX_URL    = os.getenv("MLX_SERVER_URL", "http://localhost:8080")
MODEL_NAME = os.getenv("MODEL_NAME", "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit")

# Local adapter settings (used when BACKEND=adapter)
ADAPTER_PATH = os.getenv(
    "ADAPTER_PATH",
    os.path.join(os.path.dirname(__file__), "..", "models", "adapter"),
)

# Generation params — defaults, then per-archetype overrides
_DEFAULT_PARAMS = dict(
    max_tokens=110,
    temperature=0.95,
    top_p=0.95,
    rep_pen=1.1,
    stop=["\n\n", "Subscriber:", "User:", "---", "Assistant:"],
)

# Jasmin's reply style adapts to who she's talking to:
#   cold      → short, restrained (match their energy)
#   horny     → longer, creative, hotter
#   simp      → warm, a bit longer, expressive
#   troll     → punchy, slightly unpredictable
#   whale     → focused, premium-feeling
#   cheapskate→ firm and playful, medium length
#   casual    → relaxed, conversational
_ARCHETYPE_PARAMS = {
    "cold":       dict(max_tokens=35,  temperature=0.75, top_p=0.88, rep_pen=1.0),   # short + no rep_pen
    "horny":      dict(max_tokens=130, temperature=1.05, top_p=0.95, rep_pen=1.05),
    "simp":       dict(max_tokens=130, temperature=0.9,  top_p=0.95, rep_pen=1.1),
    "troll":      dict(max_tokens=70,  temperature=1.05, top_p=0.95, rep_pen=1.0),   # punchy + no rep_pen
    "whale":      dict(max_tokens=110, temperature=0.85, top_p=0.90, rep_pen=1.1),
    "cheapskate": dict(max_tokens=100, temperature=0.95, top_p=0.95, rep_pen=1.1),
    "casual":     dict(max_tokens=115, temperature=0.9,  top_p=0.95, rep_pen=1.1),
}

# Keep only the last N turns to limit prompt size and Modal GPU time
_MAX_HISTORY_TURNS = 8

_health_cache: dict = {}


def _params(archetype_key: str) -> dict:
    return {**_DEFAULT_PARAMS, **_ARCHETYPE_PARAMS.get(archetype_key, {})}


def _trim_history(history: list[dict]) -> list[dict]:
    """Keep the last _MAX_HISTORY_TURNS message pairs to cap prompt tokens."""
    max_msgs = _MAX_HISTORY_TURNS * 2
    return history[-max_msgs:] if len(history) > max_msgs else history



# ── Local adapter backend ────────────────────────────────────────────────────
_adapter_model = None
_adapter_tokenizer = None


def _load_adapter():
    global _adapter_model, _adapter_tokenizer
    if _adapter_model is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        adapter_path = os.path.abspath(ADAPTER_PATH)
        _adapter_tokenizer = AutoTokenizer.from_pretrained(adapter_path)
        base = AutoModelForCausalLM.from_pretrained(
            "unsloth/meta-llama-3.1-8b-instruct-bnb-4bit",
            device_map="auto",
            load_in_4bit=True,
        )
        _adapter_model = PeftModel.from_pretrained(base, adapter_path)
        _adapter_model.eval()
    return _adapter_model, _adapter_tokenizer


def _stream_adapter(history: list[dict], archetype_key: str) -> Generator[str, None, None]:
    from transformers import TextIteratorStreamer

    try:
        model, tokenizer = _load_adapter()
        chat = [{"role": m["role"], "content": m["content"]} for m in history]
        is_opening = not chat
        system = get_jasmin_opening_system(archetype_key) if is_opening else get_jasmin_system(archetype_key)
        messages = [{"role": "system", "content": system}] + chat

        input_ids = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt"
        ).to(model.device)

        p = _params(archetype_key)
        streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        gen_kwargs = dict(
            input_ids=input_ids,
            streamer=streamer,
            max_new_tokens=p["max_tokens"],
            temperature=p["temperature"],
            top_p=p["top_p"],
            repetition_penalty=p["rep_pen"],
            do_sample=True,
        )
        thread = threading.Thread(target=model.generate, kwargs=gen_kwargs)
        thread.start()

        buffer = ""
        for token in streamer:
            buffer += token
            stop_hit = False
            for stop in p["stop"]:
                if stop in buffer:
                    yield buffer[: buffer.index(stop)]
                    stop_hit = True
                    break
            if stop_hit:
                break
            yield token

        thread.join()
    except Exception as e:
        msg = f"⚠️ Adapter error: {e}"
        print(msg, flush=True)
        yield msg


# ── Modal backend ─────────────────────────────────────────────────────────────
def _get_modal_model():
    import modal
    cls = modal.Cls.from_name("jasmin-inference", "JasminModel")
    return cls()


def _stream_modal(history: list[dict], archetype_key: str) -> Generator[str, None, None]:
    try:
        model = _get_modal_model()
        chat = [{"role": m["role"], "content": m["content"]} for m in _trim_history(history)]
        system = get_jasmin_opening_system(archetype_key) if not chat else get_jasmin_system(archetype_key)
        messages = [{"role": "system", "content": system}] + chat
        p = _params(archetype_key)
        for token in model.generate.remote_gen(
            messages,
            stop=p["stop"],
            max_tokens=p["max_tokens"],
            temperature=p["temperature"],
            top_p=p["top_p"],
            rep_pen=p["rep_pen"],
        ):
            yield token
    except Exception as e:
        msg = f"⚠️ Modal error: {e}"
        print(msg, flush=True)
        yield msg


# ── MLX HTTP backend ──────────────────────────────────────────────────────────
def _stream_mlx(history: list[dict], archetype_key: str) -> Generator[str, None, None]:
    import json
    import httpx

    chat = [{"role": m["role"], "content": m["content"]} for m in history]
    system = get_jasmin_opening_system(archetype_key) if not chat else get_jasmin_system(archetype_key)
    p = _params(archetype_key)
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system}] + chat,
        "stream": True,
        "max_tokens": p["max_tokens"],
        "temperature": p["temperature"],
        "top_p": p["top_p"],
        "repetition_penalty": p["rep_pen"],
        "stop": p["stop"],
    }

    try:
        with httpx.stream("POST", f"{MLX_URL}/v1/chat/completions",
                          json=payload, timeout=60.0) as resp:
            if resp.status_code != 200:
                body = resp.read().decode(errors="replace")[:300]
                msg = f"⚠️ Server error {resp.status_code}: {body}"
                print(msg, flush=True)
                yield msg
                return
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    content = json.loads(data)["choices"][0]["delta"].get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except httpx.ConnectError:
        yield f"⚠️ Cannot connect to MLX server at {MLX_URL}. Run `./start_mlx_server.sh` first."
    except Exception as e:
        msg = f"⚠️ Unexpected error: {type(e).__name__}: {e}"
        print(msg, flush=True)
        yield msg


# ── Public API ────────────────────────────────────────────────────────────────
def health_check() -> bool:
    """Check backend health. Modal result is cached for 60s to avoid per-render overhead."""
    import time
    if BACKEND == "modal":
        cached = _health_cache.get("modal")
        if cached and time.time() - cached["ts"] < 60:
            return cached["ok"]
        try:
            import modal
            modal.Cls.from_name("jasmin-inference", "JasminModel")
            result = True
        except Exception:
            result = False
        _health_cache["modal"] = {"ok": result, "ts": time.time()}
        return result
    elif BACKEND == "adapter":
        return os.path.isfile(os.path.join(os.path.abspath(ADAPTER_PATH), "adapter_config.json"))
    else:
        import httpx
        try:
            return httpx.get(f"{MLX_URL}/v1/models", timeout=2.0).status_code == 200
        except Exception:
            return False


def stream_response(history: list[dict], archetype_key: str) -> Generator[str, None, None]:
    if BACKEND == "modal":
        yield from _stream_modal(history, archetype_key)
    elif BACKEND == "adapter":
        yield from _stream_adapter(history, archetype_key)
    else:
        yield from _stream_mlx(history, archetype_key)
