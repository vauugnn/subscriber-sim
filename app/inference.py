import logging
import os
import re
from collections.abc import Callable, Generator

from archetypes import (
    ARCHETYPES,
    _SUBSCRIBER_SYSTEMS,
    get_archetype_loop_break,
    get_archetype_mid_convo_reminder,
)

# ── Logging ────────────────────────────────────────────────────────────────────
log = logging.getLogger("subscriber_sim")
if not log.handlers:
    _h = logging.StreamHandler()  # stdout → Docker logs
    _h.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    log.addHandler(_h)
    log.setLevel(logging.DEBUG if os.getenv("DEBUG") else logging.INFO)

# ── Backend ────────────────────────────────────────────────────────────────────
# All inference runs on Modal GPU (jasmin-inference app).

# Generation params — defaults (overridden per-archetype below)
_DEFAULT_PARAMS = dict(
    max_tokens=100,
    temperature=0.75,
    top_p=0.85,
    rep_pen=1.05,
    stop=["\n\nJasmin:", "\n\nUser:", "\n\n["],
)

# Per-archetype generation params from subscriber_sim_v2.ipynb
# Tighter params = more consistent archetype adherence
_ARCHETYPE_PARAMS = {
    "horny":      dict(max_tokens=80,  temperature=0.75, top_p=0.85, rep_pen=1.05),
    "cheapskate": dict(max_tokens=100, temperature=0.70, top_p=0.80, rep_pen=1.10),
    "casual":     dict(max_tokens=75,  temperature=0.65, top_p=0.80, rep_pen=1.00),
    "troll":      dict(max_tokens=85,  temperature=0.80, top_p=0.90, rep_pen=1.15),
    "whale":      dict(max_tokens=90,  temperature=0.65, top_p=0.75, rep_pen=1.05),
    "cold":       dict(max_tokens=15,  temperature=0.60, top_p=0.70, rep_pen=1.00),
    "simp":       dict(max_tokens=95,  temperature=0.75, top_p=0.85, rep_pen=1.00),
}

# Keep last 6 messages (3 full exchanges) — matches subscriber_sim_v2 context window
_MAX_HISTORY_TURNS = 6

# ── Response post-processor ────────────────────────────────────────────────────
# Removes OOC (out-of-character) artifacts — mirrors ResponseFilter from v2 notebook.

_META_PATTERNS = [
    r"(?:I'm|I am) (?:an|a) (?:AI|bot|model|language model|assistant)",
    r"(?:As an|As a) (?:AI|bot|model|language model|assistant)",
    r"I (?:should|shouldn't|need to|must|cannot|can't) ",
    r"I (?:can't|cannot) (?:roleplay|pretend)",
    r"^(?:I understand|I realize|I appreciate that)",
    r"^(?:Let me|I'll|I would) roleplay",
    r"I (?:must )?(?:maintain|keep) (?:appropriate|professional)",
]

_MAX_SENTENCES = {
    "horny": 3, "cheapskate": 3, "casual": 3,
    "troll": 2, "whale": 2,     "simp": 4, "cold": 1,
}


def _filter_response(text: str, archetype_key: str) -> str:
    """Post-process model output to strip OOC content and enforce length."""
    if not text or not text.strip():
        return text
    out = text.strip()
    # Strip hallucinated subscriber name prefixes (e.g. "JO ", "Da ", "BP ")
    out = re.sub(r"^[A-Z][A-Za-z]{0,2}\s+(?=[A-Z])", "", out)
    for pat in _META_PATTERNS:
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    out = out.strip()
    # Strip surrounding quotes
    if (out.startswith('"') and out.endswith('"')) or \
       (out.startswith("'") and out.endswith("'")):
        out = out[1:-1].strip()
    # Enforce max sentence count
    max_s = _MAX_SENTENCES.get(archetype_key, 3)
    sentences = [s.strip() for s in out.split(". ") if s.strip()]
    if len(sentences) > max_s:
        out = ". ".join(sentences[:max_s])
        if not out[-1] in ".!?":
            out += "."
    # Reduce excessive punctuation
    out = re.sub(r"([!?.♥💦🔥])\1{2,}", r"\1\1", out)
    out = re.sub(r"\.\.\.+", "..", out)
    # Strip leading action asterisks
    out = re.sub(r"^\*+\s*", "", out)
    return out.strip() or text.strip()

_health_cache: dict = {}

# ── Training data deduplication ────────────────────────────────────────────────
# Load all assistant messages from training JSONL files into a set so generated
# responses can be checked against them. Memorised training examples are rejected
# and the retry loop regenerates with higher params.

def _load_training_responses() -> set[str]:
    import json
    from pathlib import Path
    seen: set[str] = set()
    data_dir = Path(os.getenv("DATA_DIR", "/app/data"))
    if not data_dir.is_dir():
        log.info("Data dir %s not found — skipping dedup load", data_dir)
        return seen
    for jsonl_path in data_dir.glob("*.jsonl"):
        try:
            with jsonl_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    session = json.loads(line)
                    for msg in session.get("messages", []):
                        if msg.get("role") == "assistant":
                            seen.add(msg["content"].strip())
        except Exception as e:
            log.warning("Could not load training data from %s: %s", jsonl_path, e)
    log.info("Loaded %d training assistant messages for deduplication", len(seen))
    return seen


_TRAINING_RESPONSES: set[str] = _load_training_responses()


def _params(archetype_key: str) -> dict:
    return {**_DEFAULT_PARAMS, **_ARCHETYPE_PARAMS.get(archetype_key, {})}


def _trim_history(history: list[dict]) -> list[dict]:
    """Keep the last _MAX_HISTORY_TURNS message pairs to cap prompt tokens."""
    max_msgs = _MAX_HISTORY_TURNS * 2
    return history[-max_msgs:] if len(history) > max_msgs else history


def _normalize_history(history: list[dict]) -> list[dict]:
    """Trim history to cap prompt tokens.

    Training data allows assistant-first sequences (opener is always the first
    assistant turn with no preceding user message). Llama-3 chat template handles
    this natively — no seed injection needed.
    """
    return list(_trim_history(history))



# ── Modal backend ─────────────────────────────────────────────────────────────
def _get_modal_model():
    import modal
    cls = modal.Cls.from_name("jasmin-inference", "JasminModel")
    return cls()


def _is_looping(chat: list[dict], n: int = 2) -> bool:
    """Return True if the conversation is stuck in a repetition pattern.

    Detects two cases:
    - Exact repeat: last n messages from either role are identical (A,A)
    - 2-cycle alternation: subscriber rotates between two messages (A,B,A,B)
    """
    user_msgs = [m["content"].split("\n\n")[0] for m in chat if m["role"] == "user"]
    if len(user_msgs) >= n and len(set(user_msgs[-n:])) == 1:
        return True
    asst_msgs = [m["content"] for m in chat if m["role"] == "assistant"]
    # Exact repeat
    if len(asst_msgs) >= n and len(set(asst_msgs[-n:])) == 1:
        return True
    # 2-cycle: A,B,A,B — last message matches the one two steps back
    if len(asst_msgs) >= 4 and asst_msgs[-1] == asst_msgs[-3] and asst_msgs[-2] == asst_msgs[-4]:
        return True
    return False


def _inject_mid_convo_reminder(chat: list[dict], archetype_key: str, looping: bool = False) -> list[dict]:
    """Append an archetype reminder to the last user message on every turn."""
    reminder = get_archetype_mid_convo_reminder(archetype_key)
    if not reminder:
        return chat
    if looping:
        reminder += " " + get_archetype_loop_break(archetype_key)
        log.info("loop detected for [%s] — appended escalation cue", archetype_key)
    for i in range(len(chat) - 1, -1, -1):
        if chat[i]["role"] == "user":
            chat[i] = {**chat[i], "content": chat[i]["content"] + "\n\n" + reminder}
            log.info("injected mid-convo reminder for [%s] at msg index %d", archetype_key, i)
            break
    return chat


def _stream_modal(history: list[dict], archetype_key: str) -> Generator[str, None, None]:
    log.info("── stream_modal [%s] ── history: %d msgs", archetype_key, len(history))
    try:
        model = _get_modal_model()
        normalized = _normalize_history(history)
        chat = [{"role": m["role"], "content": m["content"]} for m in normalized]
        looping = _is_looping(chat)
        chat = _inject_mid_convo_reminder(chat, archetype_key, looping=looping)
        system = _SUBSCRIBER_SYSTEMS.get(archetype_key, _SUBSCRIBER_SYSTEMS["casual"])
        messages = [{"role": "system", "content": system}] + chat
        p = _params(archetype_key)
        if looping:
            p = {
                **p,
                "rep_pen":     min(p["rep_pen"] + 0.20, 1.40),
                "temperature": min(p["temperature"] + 0.15, 1.0),
            }
        log.info("system prompt: %d chars | msgs to model: %d", len(system), len(messages))
        log.info("params: max_tokens=%s temp=%.2f top_p=%.2f rep_pen=%.2f",
                 p["max_tokens"], p["temperature"], p["top_p"], p["rep_pen"])
        log.debug("last user msg: %.200s", chat[-1]["content"] if chat else "(empty)")
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
        log.error("Modal error: %s", e, exc_info=True)
        yield f"⚠️ Modal error: {e}"


# ── Public API ────────────────────────────────────────────────────────────────

# Per-archetype opener validators. Generated openers that fail the check are
# discarded and the static opener is used instead.
_OPENER_VALIDATORS: dict[str, "Callable[[str], bool]"] = {
    "cold":       lambda t: len(t.split()) <= 4,                     # "hey", "sup", "hi" only
    "simp":       lambda t: len(t.split()) >= 5,                     # must be emotionally verbose
    "horny":      lambda t: len(t.split()) >= 3,
    "cheapskate": lambda t: len(t.split()) >= 3,
    "casual":     lambda t: len(t.split()) >= 3,
    "troll":      lambda t: len(t.split()) >= 3,
    "whale":      lambda t: len(t.split()) >= 3,
}

_EXPLICIT_WORDS = {"cum", "cock", "dick", "pussy", "fuck", "suck", "sex", "nude", "nudes", "naked"}

def _opener_is_valid(text: str, archetype_key: str) -> bool:
    """Return False if the opener fails basic archetype sanity checks."""
    if not text or not text.strip():
        return False
    words = set(text.lower().split())
    # Cold openers must never be explicit
    if archetype_key == "cold" and words & _EXPLICIT_WORDS:
        log.warning("cold opener failed explicit-content check: %.60s", text)
        return False
    validator = _OPENER_VALIDATORS.get(archetype_key)
    if validator and not validator(text):
        log.warning("[%s] opener failed length check (%d words): %.60s",
                    archetype_key, len(text.split()), text)
        return False
    return True


def _static_opener(archetype_key: str) -> str:
    """Return the static opener for the archetype — fallback only."""
    return ARCHETYPES[archetype_key]["opener"]


def _generate_opener_modal(archetype_key: str) -> str:
    """Generate a fresh opener via Modal.

    Uses the bare _SUBSCRIBER_SYSTEMS prompt (identical to training) with no
    history. The model was fine-tuned to produce an archetype-correct first
    message from exactly this format — system only, no preceding user turn.

    The generation context is discarded after use; only the opener text is kept,
    so this cannot bleed into mid-conversation history.
    Falls back to the static opener on any error.
    """
    try:
        model = _get_modal_model()
        # Use the same bare system prompt as training — no role declarations,
        # no few-shots, no TASK directives. Distribution shift kills archetype fidelity.
        system = _SUBSCRIBER_SYSTEMS.get(archetype_key, _SUBSCRIBER_SYSTEMS["casual"])
        # System-only: model generates the first assistant turn with no preceding
        # user message — matches the training format exactly.
        messages = [{"role": "system", "content": system}]
        p = _params(archetype_key)
        log.info("── dynamic opener [%s] ── system: %d chars", archetype_key, len(system))
        tokens = list(model.generate.remote_gen(
            messages,
            stop=p["stop"],
            max_tokens=p["max_tokens"],
            temperature=p["temperature"] + 0.05,  # slight boost for opener variety
            top_p=p["top_p"],
            rep_pen=p["rep_pen"],
        ))
        opener = _filter_response("".join(tokens), archetype_key)
        if _opener_is_valid(opener, archetype_key):
            log.info("dynamic opener accepted: %.120s", opener)
            return opener
        log.warning("[%s] dynamic opener rejected — using static fallback", archetype_key)
    except Exception as e:
        log.error("dynamic opener failed: %s — falling back to static", e)
    return _static_opener(archetype_key)


def stream_opener(archetype_key: str) -> Generator[str, None, None]:
    """Yield a dynamically generated opener for the archetype.

    The opener is generated in isolation (no conversation history) so it cannot
    bleed into or alter mid-conversation context. Only the opener text is kept;
    the generation system prompt is discarded after use.
    """
    opener = _generate_opener_modal(archetype_key)
    log.info("── stream_opener [%s] ── %.80s", archetype_key, opener)
    yield opener


def generate_opener(archetype_key: str) -> str:
    """Return a dynamically generated opener for the archetype."""
    return _generate_opener_modal(archetype_key)


def health_check() -> bool:
    """Check Modal backend health. Result is cached for 60s to avoid per-render overhead."""
    import time
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


def stream_response(history: list[dict], archetype_key: str) -> Generator[str, None, None]:
    """Stream subscriber response tokens, then apply OOC post-processing on the full text."""
    full = "".join(_stream_modal(history, archetype_key))
    log.info("raw model output (%d chars): %.120s", len(full), full)
    filtered = _filter_response(full, archetype_key)
    log.info("filtered response (%d chars): %.120s", len(filtered), filtered)

    # Observability only — no retries (each retry = one Modal call)
    recent = [m["content"] for m in history if m["role"] == "assistant"][-4:]
    if filtered in recent:
        log.warning("[%s] response matches recent history", archetype_key)
    elif filtered in _TRAINING_RESPONSES:
        log.warning("[%s] response matches training data", archetype_key)

    yield filtered
