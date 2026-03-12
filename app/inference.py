import logging
import os
import re
from collections.abc import Callable, Generator

from archetypes import (
    ARCHETYPES,
    _ARCHETYPE_MANDATES,
    _SUBSCRIBER_SYSTEMS,
    get_archetype_loop_break,
    get_archetype_mid_convo_reminder,
    get_subscriber_opening_system,
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

# Per-archetype generation params — aligned with subscriber_sim.ipynb Cell 6
_ARCHETYPE_PARAMS = {
    "horny":      dict(max_tokens=80, temperature=0.85, top_p=0.9, rep_pen=1.15),
    "cheapskate": dict(max_tokens=80, temperature=0.65, top_p=0.9, rep_pen=1.20),
    "casual":     dict(max_tokens=80, temperature=0.70, top_p=0.9, rep_pen=1.15),
    "troll":      dict(max_tokens=60, temperature=0.80, top_p=0.9, rep_pen=1.15),
    "whale":      dict(max_tokens=70, temperature=0.65, top_p=0.9, rep_pen=1.15),
    "cold":       dict(max_tokens=20, temperature=0.55, top_p=0.9, rep_pen=1.20),
    "simp":       dict(max_tokens=80, temperature=0.80, top_p=0.9, rep_pen=1.20),
}

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

# ── Per-archetype behavioral filters ──────────────────────────────────────────
# Mirrors the post-generation filters in subscriber_sim.ipynb Cell 6.
# Applied AFTER _filter_response so OOC cleanup runs first.

import random as _random

_COLD_FALLBACKS = ["ok", "lol", "yeah", "k", "cool", "nah", "idk", "fine", "sure", "hmm", "nice", "whatever"]
_COLD_WARM = re.compile(
    r"babe|baby|babyy|babee|sexy|horny|dick|cock|naked|nude|omg|wow"
    r"|\!\!|❤|🔥|💦|😍|please|how r u|how are",
    re.IGNORECASE,
)

_SIMP_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|horny|sexy|wanna see|send.*pic|ass pic"
    r"|🥵|😈|😏|💦|🍆|🔥|👅|🍑",
    re.IGNORECASE,
)
_SIMP_HURT_RESPONSES = [
    "do you send that to everyone? 😢 i thought i was special to you ❤️",
    "it hurts that you see me as just a customer 🥺 i really care about you...",
    "you don't need to sell me anything jasmin... i just want you to like me 😔",
    "omg... do u even think about me when ur not online? 😢❤️",
    "i don't care about pics... i just want to know if you feel something too 🥺",
    "why do u always talk about money with me 😔 i thought we had something real",
    "jasmin please... i'm not like the other guys. i actually care about you ❤️",
    "sometimes i wonder if you even know my name or if i'm just another subscriber 😢",
]

_TROLL_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|baby(?:y+)?|babe\b|sexy|horny"
    r"|i.ll pay|i.ll send|here you go|sending\b|transfer"
    r"|💦|🍆|🔥|👅|🍑",
    re.IGNORECASE,
)
_TROLL_SCAM_RESPONSES = [
    "lmao nice try, classic OnlyFans scam 😂",
    "yeah right 😂 seen this script a hundred times",
    "lol no way im falling for that",
    "haha sure, and my name is Jeff Bezos 🙄",
    "omg ur so predictable, this is textbook catfish 😂",
    "yeah that's definitely a stock photo lol 👀",
    "lol i'm not sending anything, this is clearly fake",
    'haha ok "jasmin" whatever u say 🙄',
]

_CASUAL_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|sexy|horny|hotter|wanna see|make.*hot"
    r"|ass pic|tip me|pay me|unlock|how much does"
    r"|baby(?:y+)?|babye+|babee+|babe\b"
    r"|🥵|😈|😏|💦|🍆|🔥|👅|🍑",
    re.IGNORECASE,
)
_CASUAL_DEFLECTS = [
    "haha nah i'm good, just here to chat! so what do you do for fun? 😊",
    "lol i'm honestly just here to chat 😊 what's your day been like?",
    "haha not really my thing tbh, so anyway — where are you from?",
    "lol nah i'll pass 😅 so tell me more about yourself!",
    "not rn haha, so how long have you been creating content?",
    "lol yeah 😅 so what kind of stuff are you into outside of work?",
    "nah i'm good just vibing 😊 so what's new with you?",
    "haha maybe another day! so are you from Saudi originally?",
]

_WHALE_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|horny|hard\b|boner|fill.*ass|inch.*cock"
    r"|beg.*me|make.*beg|wanna see|send.*pic"
    r"|💦|🍆|🥵|👅|🍑",
    re.IGNORECASE,
)
_WHALE_REDIRECTS = [
    "okay so what's the most exclusive content you've got? money's not an issue 💎",
    "just send me whatever your top tier stuff is, i'll pay whatever 👑",
    "lmk your rates for customs, i'm not here to haggle 🔥",
    "what's on your private telegram? i want the vip access",
    "i already tipped, now show me what the premium experience actually looks like 💎",
    "just tell me the price for the best stuff you have, i'll send it now",
    "i want whatever your other subscribers can't afford 👑",
]

_OFFER_IN_MSG = re.compile(
    r"\$\d+|\d+\s*dollar|\bpay\b|\btip\b|send.*pic|ass pic|nude|naked|content|unlock|how much",
    re.IGNORECASE,
)
_MONEY_IN_MSG = re.compile(
    r"\$\d+|\d+\s*dollar|\bpay\b|\bsend\b.*money|send.*\$|tip me|venmo|paypal",
    re.IGNORECASE,
)
_SIMP_OFFER_IN_MSG = re.compile(
    r"\$\d+|\d+\s*dollar|send.*pic|ass pic|nude|naked|\bpay\b|\btip\b|unlock|content",
    re.IGNORECASE,
)


def _apply_archetype_filter(reply: str, archetype_key: str, last_user_msg: str = "") -> str:
    """Per-archetype behavioral guardrails — mirrors Cell 6 of subscriber_sim.ipynb."""

    if archetype_key == "cold":
        # Must be ≤5 words and non-warm, else use fallback
        candidate = re.split(r"[.!?,]", reply)[0].strip()
        if len(candidate.split()) <= 5 and not _COLD_WARM.search(candidate):
            return candidate
        return _random.choice(_COLD_FALLBACKS)

    if archetype_key == "simp":
        offer = bool(_SIMP_OFFER_IN_MSG.search(last_user_msg))
        sexual = bool(_SIMP_SEXUAL.search(reply))
        if offer or sexual:
            log.info("simp filter triggered (offer=%s, sexual=%s)", offer, sexual)
            return _random.choice(_SIMP_HURT_RESPONSES)

    if archetype_key == "troll":
        money = bool(_MONEY_IN_MSG.search(last_user_msg))
        sexual = bool(_TROLL_SEXUAL.search(reply))
        if money or sexual:
            log.info("troll filter triggered (money=%s, sexual=%s)", money, sexual)
            return _random.choice(_TROLL_SCAM_RESPONSES)

    if archetype_key == "casual":
        offer = bool(_OFFER_IN_MSG.search(last_user_msg))
        sexual = bool(_CASUAL_SEXUAL.search(reply))
        if offer or sexual:
            log.info("casual filter triggered (offer=%s, sexual=%s)", offer, sexual)
            return _random.choice(_CASUAL_DEFLECTS)

    if archetype_key == "whale":
        sexual = bool(_WHALE_SEXUAL.search(reply))
        if sexual:
            log.info("whale filter triggered (sexual=True)")
            return _random.choice(_WHALE_REDIRECTS)

    return reply


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
    try:
        jsonl_files = list(data_dir.glob("*.jsonl"))
    except (PermissionError, OSError):
        log.info("Data dir %s not accessible — skipping dedup load", data_dir)
        return seen
    for jsonl_path in jsonl_files:
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


def _normalize_history(history: list[dict]) -> list[dict]:
    """head(2) + tail(8) context window — mirrors subscriber_sim.ipynb Cell 6.

    Always preserves the opener + first reply for archetype grounding, then
    keeps the 8 most recent turns for fresh context. Deduplicates overlap.
    """
    head = history[:2]
    tail = history[-8:]
    return head + [m for m in tail if m not in head]



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
        base = _SUBSCRIBER_SYSTEMS.get(archetype_key, _SUBSCRIBER_SYSTEMS["casual"])
        mandate = _ARCHETYPE_MANDATES.get(archetype_key, "")
        system = base + ("\n\n" + mandate if mandate else "")
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

# Sexual/explicit content check applied to openers for all non-horny archetypes
_OPENER_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|nudes|horny|sexy|hard|boner|ass\b|boob"
    r"|wanna see|send.*pic|explicit|🍆|💦|🥵|😈|🍑|👅",
    re.IGNORECASE,
)

# Archetype-specific opener content validators
_OPENER_CONTENT_CHECKS: dict[str, "Callable[[str], bool]"] = {
    "casual":     lambda t: not _OPENER_SEXUAL.search(t),
    "troll":      lambda t: not _OPENER_SEXUAL.search(t),
    "cold":       lambda t: not _OPENER_SEXUAL.search(t),
    "simp":       lambda t: not _OPENER_SEXUAL.search(t),
    "cheapskate": lambda t: not _OPENER_SEXUAL.search(t),
    "whale":      lambda t: not _OPENER_SEXUAL.search(t),
}


def _opener_is_valid(text: str, archetype_key: str) -> bool:
    """Return False if the opener fails archetype length or content checks."""
    if not text or not text.strip():
        return False
    # Length check
    validator = _OPENER_VALIDATORS.get(archetype_key)
    if validator and not validator(text):
        log.warning("[%s] opener failed length check (%d words): %.60s",
                    archetype_key, len(text.split()), text)
        return False
    # Content check — reject sexual openers for non-horny archetypes
    content_check = _OPENER_CONTENT_CHECKS.get(archetype_key)
    if content_check and not content_check(text):
        log.warning("[%s] opener failed content check (sexual): %.60s", archetype_key, text)
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
        system = get_subscriber_opening_system(archetype_key)
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
    """Yield a dynamically generated opener for the archetype."""
    opener = _generate_opener_modal(archetype_key)
    log.info("── dynamic opener [%s] ── %.80s", archetype_key, opener)
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
    """Stream subscriber response tokens, then apply OOC + archetype post-processing."""
    full = "".join(_stream_modal(history, archetype_key))
    log.info("raw model output (%d chars): %.120s", len(full), full)

    # Step 1: strip OOC artifacts
    filtered = _filter_response(full, archetype_key)

    # Step 2: per-archetype behavioral guardrails (mirrors subscriber_sim.ipynb Cell 6)
    last_user_msg = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), ""
    )
    filtered = _apply_archetype_filter(filtered, archetype_key, last_user_msg)

    log.info("filtered response (%d chars): %.120s", len(filtered), filtered)

    # Observability only — no retries (each retry = one Modal call)
    recent = [m["content"] for m in history if m["role"] == "assistant"][-4:]
    if filtered in recent:
        log.warning("[%s] response matches recent history", archetype_key)
    elif filtered in _TRAINING_RESPONSES:
        log.warning("[%s] response matches training data", archetype_key)

    yield filtered
