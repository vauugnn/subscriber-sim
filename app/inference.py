import logging
import os
import re
import sys
from collections.abc import Callable, Generator

# Ensure local modules (archetypes, database) are importable regardless of
# how this file is loaded (Streamlit Cloud, Docker, local venv)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from archetypes import (
    ARCHETYPES,
    _ARCHETYPE_MANDATES,
    _SUBSCRIBER_SYSTEMS,
    get_archetype_loop_break,
    get_archetype_mid_convo_reminder,
    get_opener_prefill,
    get_subscriber_opening_system,
    get_subscriber_prefill,
    get_subscriber_system,
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
# INFERENCE_BACKEND=modal  → Modal GPU (production / Render)
# INFERENCE_BACKEND=mlx    → local mlx_lm.server (Mac M-series, run start_mlx_server.sh first)
# INFERENCE_BACKEND=peft   → local PEFT adapter with smart device selection (Mac/Linux)
_INFERENCE_BACKEND = os.getenv("INFERENCE_BACKEND", "modal").lower()
_MLX_SERVER_URL = os.getenv("MLX_SERVER_URL", "http://localhost:8080").rstrip("/")
_MLX_MODEL_ID = os.getenv("MLX_MODEL_ID", "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit")
_PEFT_ADAPTER_PATH = os.getenv("PEFT_ADAPTER_PATH", "models/lora-adapter")
_PEFT_BASE_MODEL = os.getenv("PEFT_BASE_MODEL", "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit")

# ── Device selection for PEFT (intelligent GPU/CPU choice on Mac) ─────────────
def _select_device() -> str:
    """Select optimal device: CUDA > MPS (Mac 16GB+) > CPU."""
    import torch
    import platform

    # Try CUDA first (Linux/Windows with GPU)
    if torch.cuda.is_available():
        log.info("Using CUDA device")
        return "cuda"

    # Try MPS on Mac if sufficient RAM (>= 16GB physical RAM)
    if torch.backends.mps.is_available() and platform.system() == "Darwin":
        try:
            import psutil
            total_ram_gb = psutil.virtual_memory().total / (1024**3)
            if total_ram_gb >= 16:
                log.info(f"Mac detected with {total_ram_gb:.1f}GB RAM — using MPS GPU")
                return "mps"
        except ImportError:
            # psutil not available; use heuristic: if mps is available on Mac, likely has enough RAM
            log.info("Using MPS (Mac GPU)")
            return "mps"

    # Fall back to CPU
    log.info("Using CPU device")
    return "cpu"

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
    "horny":      dict(max_tokens=80, temperature=0.85, top_p=0.9, rep_pen=1.35),
    "cheapskate": dict(max_tokens=80, temperature=0.70, top_p=0.9, rep_pen=1.35),
    "casual":     dict(max_tokens=55, temperature=0.72, top_p=0.9, rep_pen=1.35),
    "troll":      dict(max_tokens=60, temperature=0.85, top_p=0.9, rep_pen=1.40),
    "whale":      dict(max_tokens=70, temperature=0.70, top_p=0.9, rep_pen=1.35),
    "cold":       dict(max_tokens=20, temperature=0.60, top_p=0.9, rep_pen=1.30),
    "simp":       dict(max_tokens=50, temperature=0.82, top_p=0.9, rep_pen=1.35),
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

# Leaked instruction fragments — mid-convo reminder text the model echoes back
_INSTRUCTION_LEAK_PATTERNS = [
    r"\[STAY IN CHARACTER[^\]]*\]",          # full reminder block
    r"—\s*react to that as your character",  # partial echo of reminder
    r"Respond to THAT specifically",
    r"She just said:",                        # snippet injection prefix
    r"\[NEW SUBSCRIBER\]",                   # opener trigger leaked
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
    # Strip hallucinated HTML/XML tags from training data leakage
    out = re.sub(r"<[^>]+>", "", out)
    # Strip newline-delimited name artifacts from training data (e.g. "Wi\nhi😍" → "hi😍")
    out = re.sub(r"^[A-Za-z]{1,4}\n+", "", out)
    # Strip hallucinated subscriber name prefixes (e.g. "JO ", "Da ", "BP ")
    out = re.sub(r"^[A-Z][A-Za-z]{0,2}\s+(?=[A-Z])", "", out)
    for pat in _META_PATTERNS:
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    for pat in _INSTRUCTION_LEAK_PATTERNS:
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    out = out.strip()
    # Strip surrounding quotes
    if (out.startswith('"') and out.endswith('"')) or \
       (out.startswith("'") and out.endswith("'")):
        out = out[1:-1].strip()
    # Enforce max sentence count — split on all sentence-ending punctuation
    max_s = _MAX_SENTENCES.get(archetype_key, 3)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", out) if s.strip()]
    if len(sentences) > max_s:
        out = " ".join(sentences[:max_s])
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

# ── OOC detection patterns (reply content) ───────────────────────────────────

# global: subscriber acting as Jasmin (role reversal) — applies to ALL archetypes
_ROLE_REVERSAL = re.compile(
    r"send me \$\d+|send me \d+\s*dollar"          # asking for payment
    r"|i can give you|i.ll give you"                # offering content
    r"|what do (u|you) think of my (ass|body|tits|cock|dick|content|page)"
    r"|im almost naked|i.m almost naked|i am almost naked|i.m naked rn"
    r"|wanna see my (ass|body|tits|page|content)"   # offering to show their own content
    r"|my OF\b|my onlyfans|tip me|pay me \$"
    r"|you (have to|need to|gotta|must) pay"        # creator telling subscriber to pay
    r"|i have (videos?|pics?|content|customs?) for (you|u)"  # creator offering own content
    r"|i.m not (gonna|going to) give it away"       # creator refusing freebies
    r"|not (giving|gonna give) (it|this|that) away" # same pattern variation
    r"|it.s (a little |kinda |pretty )?(expensive|pricey|not cheap)"  # creator setting price
    r"|that.s (what|why) (my|the) (page|OF|onlyfans) is for"  # creator promoting page
    r"|i (have|got) (something|stuff|content|videos?) (for you|u can)"   # creator offering
    r"|wanna see (it|this|my|what i)",                                   # creator teasing own content
    re.IGNORECASE,
)

# Creator-voice phrases that are OOC for archetypes that never create/discount content.
# NOT applied to whale (legitimately says "i'll send it" = paying) or
# cheapskate (legitimately says "i can do that" = agreeing to a deal).
_CREATOR_VOICE = re.compile(
    r"i.ll give (it|that) cheaper|i can do (it|that) cheaper"   # creator offering discount
    r"|i.ll (make|post|create|upload|record) (it|that|more|this|the vid|the pic)"  # creator making content
    r"|how many (videos?|pics?|customs?|posts?) i (will|.ll|can|do|am)",            # creator output talk
    re.IGNORECASE,
)
_CREATOR_VOICE_ARCHETYPES = {"horny", "casual", "troll", "cold", "simp", "cheapskate", "whale"}

# cold: block warm/sexual words — reply must be ≤5 words and neutral
_COLD_WARM = re.compile(
    r"babe|baby|babyy|babee|sexy|horny|dick|cock|naked|nude"
    r"|💦|😍|😘|🥵|🍆|👅|🍑",
    re.IGNORECASE,
)

# horny: block cheapskate haggling, troll skepticism, simp love-bombing
_HORNY_OOC = re.compile(
    r"\bbroke\b|can.t afford|too expensive|too much|what a rip|discount|cheaper"
    r"|that.s fake|not real|catfish|show proof|is this a bot"
    r"|i love you|you.re perfect|i adore you|miss you so much|u mean everything",
    re.IGNORECASE,
)

# cheapskate: block whale spending freely, simp emotional attachment
_CHEAPSKATE_OOC = re.compile(
    r"money.s not an issue|budget.s not a concern|i.ll pay anything|no problem with the price"
    r"|just send it|i.ll take it all|sending now \$\d{3}"   # whale behaviour
    r"|i love you|you.re perfect|i adore|miss you so much",  # simp drift
    re.IGNORECASE,
)

# simp: block explicit sexual content and transactional talk
_SIMP_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|horny|sexy|wanna see|send.*pic|ass pic"
    r"|🥵|😈|😏|💦|🍆|👅|🍑",
    re.IGNORECASE,
)
_SIMP_COLD = re.compile(        # simp should never be cold or dismissive
    r"^(k|ok|lol|sure|whatever|idc|cool|nice|fine|yeah|nah|mhm|ight)\s*[.!?]?$",
    re.IGNORECASE,
)

# troll: block sexual content, paying/sending money, being genuinely warm
_TROLL_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|baby(?:y+)?|babe\b|sexy|horny"
    r"|i.ll pay|i.ll send|here you go|sending\b|transfer"
    r"|💦|🍆|👅|🍑",
    re.IGNORECASE,
)
_TROLL_WARM = re.compile(       # troll should never be sincerely complimentary
    r"you.re (so |really )?(beautiful|gorgeous|stunning|perfect|amazing|wonderful)"
    r"|ur literally so hot|i love (you|ur page)|ur my favou?rite",
    re.IGNORECASE,
)

# casual: block explicit sexual content
_CASUAL_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|sexy|horny|hotter|wanna see|make.*hot"
    r"|ass pic|tip me|pay me|unlock"
    r"|🥵|😈|😏|💦|🍆|👅|🍑",
    re.IGNORECASE,
)

# whale: block explicit sexual content, cheapskate haggling, simp drift
_WHALE_SEXUAL = re.compile(
    r"dick|cock|cum|fuck|naked|nude|horny|get.*hard|so hard|boner|fill.*ass|inch.*cock"
    r"|beg.*me|make.*beg|wanna see u naked|send.*nude"
    r"|💦|🍆|🥵|👅|🍑",
    re.IGNORECASE,
)
_WHALE_OOC = re.compile(
    r"\bbroke\b|can.t afford|too (much|expensive)|discount|cheaper|half.?price"
    r"|\$[1-4]\d\b|\$\d\b"          # amounts under $50 — whale never haggles small
    r"|get closer|xoxo|lovey|babee|get to know (you|u)\b|let.s see when",
    re.IGNORECASE,
)

# ── OOC detection patterns (Jasmin's last message) ────────────────────────────

_OFFER_IN_MSG = re.compile(     # triggers casual filter
    r"\$\d+|\d+\s*dollar|\bpay\b|send.*pic|ass pic|nude|naked|how much does|how much for|unlock",
    re.IGNORECASE,
)
_MONEY_IN_MSG = re.compile(     # triggers troll filter
    r"\$\d+|\d+\s*dollar|\bpay\b|\bsend\b.*money|send.*\$|tip me|venmo|paypal",
    re.IGNORECASE,
)
_SIMP_OFFER_IN_MSG = re.compile(  # triggers simp filter
    r"\$\d+|\d+\s*dollar|send.*pic|ass pic|nude|naked|\bpay\b|unlock",
    re.IGNORECASE,
)

# ── OOC fallback pools ────────────────────────────────────────────────────────
# Used ONLY when OOC filter trips. Large pools + _pick_fresh keep repetition rare.

_COLD_FALLBACKS = [
    "ok", "lol", "yeah", "k", "cool", "nah", "idk", "fine", "sure",
    "hmm", "nice", "whatever", "mhm", "ight", "true", "yep", "eh",
    "right", "guess so", "k cool", "ok sure", "lol ok",
]

_HORNY_FALLBACKS = [
    "okay but ur page has me distracted rn 😩",
    "i need to see more of u asap 🔥",
    "can we do a custom? i've been thinking about it 😏",
    "ur so fucking hot ngl 🥵",
    "i want the full vid, how do i get it 😩",
    "what does a custom from u look like 🔥",
    "u got me hooked fr 😏",
    "i've been on ur page for an hour and i can't stop 🥵",
    "i need a custom vid asap what do i do 🔥",
    "ur the hottest creator i've seen no cap 😍",
    "u literally have me going crazy rn 😩",
    "i want everything on ur page tbh 🔥",
    "do u do voice notes too? asking for obvious reasons 😏",
    "ur making this very hard for me rn 😩",
    "i've already replayed that preview like 10 times 🥵",
]

_CHEAPSKATE_FALLBACKS = [
    "that's still too much tbh, other girls charge way less",
    "what about half price? i'm a loyal sub 😭",
    "can i at least get a free preview first?",
    "lol that's a lot, any discount for new subs?",
    "i'll tip u later if i like it, can i see first?",
    "other creators charge like $10 for the same thing",
    "can we negotiate? i'm not made of money lol",
    "okay what's the cheapest thing u offer rn",
    "that price tho 😬 can u do better?",
    "what if i'm a regular? do loyal subs get deals?",
    "lmao okay what about a bundle deal?",
    "i'll sub for a year if u give me a discount on this",
    "that feels steep ngl, is there a sale coming up?",
    "can u do like half of that? that's all i got rn 😭",
    "i'll come back when i have more cash, unless u can work with me?",
]

_TROLL_FALLBACKS = [
    "lol there's no way ur real 😂",
    "yeah right, seen this a hundred times",
    "lol okay 'jasmin' sure 🙄",
    "prove ur real first then we'll talk",
    "classic OF catfish energy right here 😂",
    "lmao not falling for that",
    "wait so ur telling me this isn't a bot 😂",
    "bro imagine actually believing this 💀",
    "okay and??? 😂",
    "sounds fake ngl 🙄",
    "lol bold of u to assume",
    "yeah whatever u say 😂",
    "interesting try tho 😂",
    "lol okay sure jan",
    "sus 😂",
    "i've seen this script before",
    "wait ur actually responding? shocked 😂",
    "nah that's cap",
    "sure buddy 🙄",
    "lmao okay",
    "right right 😂",
    "totally believe u 🙄",
    "uh huh sure",
    "okay scammer 😂",
    "nope not buying it",
]

_SIMP_FALLBACKS = [
    "do u send that to everyone? 😢 i thought i was different",
    "it hurts when u talk like that... i actually care about u 🥺",
    "i don't want content i just want u to know i'm here for u ❤️",
    "do u even think about me when ur offline? 😢",
    "why does it always come back to money with u... 😔",
    "i'm not like other subscribers jasmin i genuinely care",
    "sometimes i wonder if u even know my name 😢",
    "i just want to feel like i matter to u 🥺❤️",
    "that made my heart drop a little ngl 😔",
    "u don't have to sell me anything... i just like talking to u",
    "can we just talk for once without it being about content 😢",
    "i've been thinking about u all day and then u say that 😔",
    "i'm not just a subscriber to u right? 🥺",
    "that hurt a little not gonna lie ❤️",
    "i care about u more than u probably know 😢",
]

_CASUAL_FALLBACKS = [
    "haha nah i'm good, just here to chat! what do u do for fun? 😊",
    "lol i'm honestly just here to vibe 😊 how's ur day been?",
    "haha not really my thing tbh, so anyway — where are u from?",
    "lol nah i'll pass 😅 tell me more about yourself though!",
    "not rn haha, so how long have u been on here?",
    "lol yeah 😅 so what are u into outside of work?",
    "nah i'm good just chillin 😊 what's new with u?",
    "haha maybe another time! are u originally from Saudi?",
    "lol that's funny, so what's ur day actually like?",
    "haha i'm just here to talk honestly 😊 how are u doing?",
    "lol nah not my thing, so do u have hobbies outside this?",
    "haha okay okay 😅 so what's something random about u?",
    "lol i'll pass on that one 😊 so where do u live now?",
    "not tonight haha, so what kind of music do u like?",
    "nah i'm just here for the convo honestly 😊",
]

_WHALE_FALLBACKS = [
    "okay what's ur most exclusive content? money's not an issue 💎",
    "just send me whatever ur top tier stuff is, i'll pay whatever 👑",
    "lmk ur rates for customs, i'm not here to haggle",
    "what's on ur private channel? i want the vip access",
    "i already tipped — what does the premium experience look like 💎",
    "just tell me the price for the best stuff u have, sending now",
    "i want whatever ur other subscribers can't afford 👑",
    "okay skip the basics — what's actually exclusive on ur page?",
    "money's fine, just tell me what u got at the top level 💎",
    "not interested in the standard stuff, what's ur best? 👑",
    "just quote me for the most premium thing u offer",
    "i'll take the custom, what info do u need from me 💎",
    "ur page is solid — what do vip subs actually get?",
    "tip's incoming, just lmk what's worth it at the top 👑",
    "i don't do budgets, just send me something exclusive 💎",
]


def _pick_fresh(pool: list[str], recent: set[str]) -> str:
    """Pick a random item from pool, preferring ones not in recent."""
    fresh = [x for x in pool if x not in recent]
    return _random.choice(fresh if fresh else pool)


def _try_salvage(reply: str) -> str | None:
    """Option C: Extract the first sentence before the OOC content.

    Returns the first sentence if it's >= 3 words, otherwise None.
    Only used before falling back to the static pool — preserves conversational
    value when the beginning of a reply is in-character but the tail goes OOC.
    """
    sentences = re.split(r"(?<=[.!?])\s+", reply.strip())
    first = sentences[0].strip() if sentences else ""
    return first if len(first.split()) >= 3 else None


def _apply_archetype_filter(reply: str, archetype_key: str, last_user_msg: str, recent: set[str]) -> str:
    """Per-archetype OOC guard. Returns the original reply if in-character, else a fresh fallback."""

    # Global role-reversal check — subscriber must NEVER act as Jasmin (ask for money,
    # offer their own content, describe their own body). Applies before per-archetype checks.
    _ROLE_REVERSAL_FALLBACKS = {
        "horny":      _HORNY_FALLBACKS,
        "cheapskate": _CHEAPSKATE_FALLBACKS,
        "casual":     _CASUAL_FALLBACKS,
        "troll":      _TROLL_FALLBACKS,
        "whale":      _WHALE_FALLBACKS,
        "cold":       _COLD_FALLBACKS,
        "simp":       _SIMP_FALLBACKS,
    }
    if _ROLE_REVERSAL.search(reply):
        log.info("[%s] role-reversal filter triggered", archetype_key)
        salvaged = _try_salvage(reply)
        if salvaged and not _ROLE_REVERSAL.search(salvaged):
            log.info("[%s] role-reversal salvaged first sentence: %.60s", archetype_key, salvaged)
            return salvaged
        fallback_pool = _ROLE_REVERSAL_FALLBACKS.get(archetype_key, _CASUAL_FALLBACKS)
        return _pick_fresh(fallback_pool, recent)

    if archetype_key in _CREATOR_VOICE_ARCHETYPES and _CREATOR_VOICE.search(reply):
        log.info("[%s] creator-voice filter triggered", archetype_key)
        salvaged = _try_salvage(reply)
        if salvaged and not _CREATOR_VOICE.search(salvaged) and not _ROLE_REVERSAL.search(salvaged):
            log.info("[%s] creator-voice salvaged first sentence: %.60s", archetype_key, salvaged)
            return salvaged
        fallback_pool = _ROLE_REVERSAL_FALLBACKS.get(archetype_key, _CASUAL_FALLBACKS)
        return _pick_fresh(fallback_pool, recent)

    if archetype_key == "cold":
        candidate = re.split(r"[.!?,]", reply)[0].strip()
        if len(candidate.split()) <= 5 and not _COLD_WARM.search(candidate):
            return candidate
        return _pick_fresh(_COLD_FALLBACKS, recent)

    if archetype_key == "horny":
        if _HORNY_OOC.search(reply):
            log.info("horny OOC filter triggered")
            salvaged = _try_salvage(reply)
            if salvaged and not _HORNY_OOC.search(salvaged) and not _ROLE_REVERSAL.search(salvaged):
                log.info("horny salvaged first sentence: %.60s", salvaged)
                return salvaged
            return _pick_fresh(_HORNY_FALLBACKS, recent)

    if archetype_key == "cheapskate":
        if _CHEAPSKATE_OOC.search(reply):
            log.info("cheapskate OOC filter triggered")
            salvaged = _try_salvage(reply)
            if salvaged and not _CHEAPSKATE_OOC.search(salvaged) and not _ROLE_REVERSAL.search(salvaged):
                log.info("cheapskate salvaged first sentence: %.60s", salvaged)
                return salvaged
            return _pick_fresh(_CHEAPSKATE_FALLBACKS, recent)

    if archetype_key == "simp":
        if _SIMP_OFFER_IN_MSG.search(last_user_msg) or _SIMP_SEXUAL.search(reply) or _SIMP_COLD.search(reply.strip()):
            log.info("simp OOC filter triggered")
            salvaged = _try_salvage(reply)
            if salvaged and not _SIMP_SEXUAL.search(salvaged) and not _SIMP_COLD.search(salvaged.strip()) and not _ROLE_REVERSAL.search(salvaged):
                log.info("simp salvaged first sentence: %.60s", salvaged)
                return salvaged
            return _pick_fresh(_SIMP_FALLBACKS, recent)

    if archetype_key == "troll":
        if _MONEY_IN_MSG.search(last_user_msg) or _TROLL_SEXUAL.search(reply) or _TROLL_WARM.search(reply):
            log.info("troll OOC filter triggered")
            salvaged = _try_salvage(reply)
            if salvaged and not _TROLL_SEXUAL.search(salvaged) and not _TROLL_WARM.search(salvaged) and not _ROLE_REVERSAL.search(salvaged):
                log.info("troll salvaged first sentence: %.60s", salvaged)
                return salvaged
            return _pick_fresh(_TROLL_FALLBACKS, recent)

    if archetype_key == "casual":
        if _OFFER_IN_MSG.search(last_user_msg) or _CASUAL_SEXUAL.search(reply):
            log.info("casual OOC filter triggered")
            salvaged = _try_salvage(reply)
            if salvaged and not _CASUAL_SEXUAL.search(salvaged) and not _ROLE_REVERSAL.search(salvaged):
                log.info("casual salvaged first sentence: %.60s", salvaged)
                return salvaged
            return _pick_fresh(_CASUAL_FALLBACKS, recent)

    if archetype_key == "whale":
        if _WHALE_SEXUAL.search(reply) or _WHALE_OOC.search(reply):
            log.info("whale OOC filter triggered (sexual=%s, ooc=%s)",
                     bool(_WHALE_SEXUAL.search(reply)), bool(_WHALE_OOC.search(reply)))
            salvaged = _try_salvage(reply)
            if salvaged and not _WHALE_SEXUAL.search(salvaged) and not _WHALE_OOC.search(salvaged) and not _ROLE_REVERSAL.search(salvaged):
                log.info("whale salvaged first sentence: %.60s", salvaged)
                return salvaged
            return _pick_fresh(_WHALE_FALLBACKS, recent)

    return reply


_health_cache: dict = {}

# ── Keep-warm background thread ───────────────────────────────────────────────
# Modal containers go cold after ~5 min of inactivity. We fire a max_tokens=1
# ping every 4 minutes from a daemon thread so the container stays hot even
# when the user is idle. Daemon=True means it dies with the main process.

import threading as _threading
import time as _time

_KEEP_WARM_INTERVAL = int(os.getenv("KEEP_WARM_INTERVAL", "240"))  # seconds


def _keep_warm_ping() -> None:
    try:
        model = _get_modal_model()
        gen = model.generate.remote_gen(
            [{"role": "user", "content": "hi"}],
            stop=["\n"],
            max_tokens=1,
            temperature=0.1,
            top_p=0.9,
            rep_pen=1.0,
        )
        next(gen, None)  # consume one token — just enough to touch the container
        _health_cache["modal"] = {"ok": True, "ts": _time.time()}
        log.debug("keep-warm ping OK")
    except Exception as e:
        _health_cache["modal"] = {"ok": False, "ts": _time.time()}
        log.warning("keep-warm ping failed: %s", e)


def _keep_warm_loop() -> None:
    import random as _rand
    # Jitter spreads multiple worker processes so they don't all ping simultaneously.
    # Each worker gets a random delay between 10–70s before its first ping.
    _time.sleep(10 + _rand.randint(0, 60))
    while True:
        _keep_warm_ping()
        _time.sleep(_KEEP_WARM_INTERVAL)


_warm_thread = _threading.Thread(target=_keep_warm_loop, daemon=True, name="modal-keep-warm")
_warm_thread.start()

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
    """tail(16) context window — contiguous recent turns, no gap.

    Increased from 8 to 16 messages (8 turns) to prevent context drift in LoRA inference.
    The additional context prevents the model from losing archetype consistency mid-conversation.
    Archetype grounding is reinforced by [CONV STATE] + mid-convo reminder + system prompt re-injection.
    
    Training sessions were typically 5-10 turns, but Streamlit conversations can extend 15+ turns.
    The larger window is necessary for LoRA adapters to maintain character over extended conversations.
    """
    return history[-16:]


def _build_messages_with_system_reinject(
    chat: list[dict],
    archetype_key: str,
    char_state: str | None = None,
) -> list[dict]:
    """Build message list with periodic system prompt re-injection.
    
    Re-injects the full system prompt every 2 assistant turns to prevent
    LoRA prompt decay in extended conversations. This is critical for maintaining
    character consistency over 12+ turns.
    
    Args:
        chat: Normalized conversation history (already processed)
        archetype_key: Subscriber archetype (used to fetch system prompt)
        char_state: Optional enhanced character state string to append to system
    
    Returns:
        List of messages with system prompt strategically re-injected
    """
    system = get_subscriber_system(archetype_key)
    if char_state:
        system += "\n\n" + char_state
    
    # Count assistant turns to determine re-injection points
    asst_turns = sum(1 for m in chat if m["role"] == "assistant")
    
    # Always prepend system at the start
    messages = [{"role": "system", "content": system}]
    
    # Add chat messages, re-injecting system every 2 assistant turns
    for i, msg in enumerate(chat):
        messages.append(msg)
        
        # Check if we should inject system prompt after this message
        if msg["role"] == "assistant":
            # Count assistant turns up to this point
            asst_count = sum(1 for m in chat[:i+1] if m["role"] == "assistant")
            # Re-inject after every 2nd assistant turn (at turns 2, 4, 6, 8, etc.)
            if asst_count > 0 and asst_count % 2 == 0:
                # Insert system prompt before the next user message (if it exists)
                # This maintains Llama-3 alternation (system → user → assistant → user → ...)
                if i + 1 < len(chat) and chat[i + 1]["role"] == "user":
                    messages.append({"role": "system", "content": system})
                    log.debug("re-injected system prompt after assistant turn %d", asst_count)
    
    return messages


# ── MLX local backend ─────────────────────────────────────────────────────────
def _mlx_chat(messages: list[dict], *, max_tokens: int, temperature: float, top_p: float, rep_pen: float) -> str:
    """POST to local mlx_lm.server and return full response text."""
    import httpx
    payload = {
        "model": _MLX_MODEL_ID,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "repetition_penalty": rep_pen,
        "stream": False,
    }
    resp = httpx.post(f"{_MLX_SERVER_URL}/v1/chat/completions", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _stream_mlx(history: list[dict], archetype_key: str, cached_state: dict | None = None) -> Generator[str, None, None]:
    log.info("── stream_mlx [%s] ── history: %d msgs", archetype_key, len(history))
    try:
        last_user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        char_state = _build_character_state_str(cached_state or {}, archetype_key, last_user_msg)
        normalized = _normalize_history(history)
        chat = [{"role": m["role"], "content": m["content"]} for m in normalized]
        # Llama-3 chat template requires user→assistant alternation.
        # If the history starts with the opener (assistant), prepend the same
        # synthetic user turn used during opener generation.
        if chat and chat[0]["role"] == "assistant":
            chat = [{"role": "user", "content": "[NEW SUBSCRIBER]"}] + chat
        looping = _is_looping(chat)
        chat = _inject_mid_convo_reminder(chat, archetype_key, looping=looping)
        
        # Use new helper for system prompt re-injection every 2 turns
        messages = _build_messages_with_system_reinject(chat, archetype_key, char_state)
        
        prefill = get_subscriber_prefill(archetype_key)
        if prefill and (not messages or messages[-1]["role"] != "assistant"):
            messages.append({"role": "assistant", "content": prefill})
        p = _params(archetype_key)
        if looping:
            p = {**p, "rep_pen": min(p["rep_pen"] + 0.20, 1.40), "temperature": min(p["temperature"] + 0.15, 1.0)}
        log.info("MLX params: max_tokens=%s temp=%.2f top_p=%.2f rep_pen=%.2f | msgs: %d", 
                 p["max_tokens"], p["temperature"], p["top_p"], p["rep_pen"], len(messages))
        yield _mlx_chat(messages, max_tokens=p["max_tokens"], temperature=p["temperature"], top_p=p["top_p"], rep_pen=p["rep_pen"])
    except Exception as e:
        log.error("MLX server error: %s", e, exc_info=True)
        yield f"⚠️ MLX error: {e}"


def _generate_opener_mlx(archetype_key: str) -> str:
    try:
        system = get_subscriber_opening_system(archetype_key)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "[NEW SUBSCRIBER]"},
        ]
        p = _params(archetype_key)
        for attempt in range(3):
            p_attempt = {**p, "rep_pen": min(p["rep_pen"] + attempt * 0.15, 1.5), "temperature": p["temperature"] + 0.05}
            raw = _mlx_chat(messages, max_tokens=p_attempt["max_tokens"], temperature=p_attempt["temperature"], top_p=p_attempt["top_p"], rep_pen=p_attempt["rep_pen"])
            opener = _filter_response(raw, archetype_key)
            if _opener_is_valid(opener, archetype_key):
                log.info("MLX opener accepted (attempt %d): %.120s", attempt + 1, opener)
                return opener
            log.warning("[%s] MLX opener attempt %d rejected: %.80s", archetype_key, attempt + 1, opener)
        log.warning("[%s] all MLX opener attempts failed — using pool fallback", archetype_key)
    except Exception as e:
        log.error("MLX opener failed: %s — falling back to pool", e)
    return _static_opener(archetype_key)


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
    """Append an archetype reminder to the last user message.

    Only injects after turn 3 (gives the model room to respond naturally early on)
    or immediately when a loop is detected.
    """
    if not looping:
        # Count subscriber (assistant) turns so far
        turns = sum(1 for m in chat if m["role"] == "assistant")
        if turns < 3:
            return chat

    reminder = get_archetype_mid_convo_reminder(archetype_key)
    if not reminder:
        return chat

    # Option A: enrich the reminder with Jasmin's actual last message so the model
    # is explicitly told what to respond to, not just reminded of its archetype.
    last_user_content = next(
        (m["content"].split("\n\n")[0].strip() for m in reversed(chat) if m["role"] == "user"),
        "",
    )
    if last_user_content:
        snippet = last_user_content[:80]
        # Append the context clause just before the closing bracket
        reminder = reminder.rstrip("]") + f' She just said: "{snippet}". Respond to THAT specifically.]'

    if looping:
        reminder += " " + get_archetype_loop_break(archetype_key)
        log.info("loop detected for [%s] — appended escalation cue", archetype_key)
    for i in range(len(chat) - 1, -1, -1):
        if chat[i]["role"] == "user":
            chat[i] = {**chat[i], "content": chat[i]["content"] + "\n\n" + reminder}
            log.info("injected mid-convo reminder for [%s] at msg index %d", archetype_key, i)
            break
    return chat


_ESCALATION_KEYWORDS: dict[str, list[str]] = {
    "horny":      ["custom", "vid", "video", "pic", "naked", "want", "need", "asap", "more", "now"],
    "cheapskate": ["discount", "cheaper", "less", "half", "broke", "afford", "deal", "negotiate", "free", "preview"],
    "troll":      ["fake", "catfish", "bot", "prove", "scam", "cap", "sus", "lying", "real"],
    "whale":      ["exclusive", "vip", "premium", "best", "custom", "private", "top", "everything"],
    "simp":       ["love", "care", "miss", "heart", "feel", "matter", "different", "think about you"],
    "cold":       [],
    "casual":     [],
}

_MILESTONE_KEYWORDS: dict[str, list[str]] = {
    "horny":      ["custom"],
    "cheapskate": ["discount", "cheaper", "negotiate", "half", "free"],
    "troll":      ["fake", "catfish", "bot", "scam", "cap"],
    "simp":       ["love", "care", "miss", "heart"],
    "whale":      ["exclusive", "vip", "premium", "custom", "best"],
    "cold":       [],
    "casual":     [],
}


def update_character_state(cached: dict, new_msg: str, archetype_key: str) -> dict:
    """Incrementally update the cached character state with one new assistant message.

    O(1) — only scans the single new message, merges counts into the cache.
    The cache dict is stored in DB and passed in; this function returns the updated version.
    """
    text = new_msg.lower()
    state = dict(cached)  # shallow copy — don't mutate the caller's dict
    state["turns"] = state.get("turns", 0) + 1
    milestone_kws = _MILESTONE_KEYWORDS.get(archetype_key, [])
    state["milestones"] = state.get("milestones", 0) + sum(1 for kw in milestone_kws if kw in text)
    esc_kws = _ESCALATION_KEYWORDS.get(archetype_key, [])
    state["recent_hits"] = sum(1 for kw in esc_kws if kw in text)  # per-turn, not cumulative
    return state


def _build_character_state_str(state: dict, archetype_key: str, last_user_msg: str = "") -> str | None:
    """Render the cached state dict into a system-prompt string.

    Returns None when the conversation is too short to need grounding (< 4 turns).
    """
    turn_count = state.get("turns", 0)
    if turn_count < 4:
        return None

    hits = state.get("recent_hits", 0)
    escalation = "high" if hits >= 4 else ("medium" if hits >= 2 else "baseline")
    milestone_count = state.get("milestones", 0)
    milestone_str = f" Key signals seen: {milestone_count}x." if milestone_count >= 2 else ""

    # Option B: anchor the [CONV STATE] block to Jasmin's actual last message so the
    # system prompt reinforces what the mid-convo reminder already says.
    last_said_str = ""
    if last_user_msg:
        snippet = last_user_msg[:80].strip()
        last_said_str = f' Jasmin just said: "{snippet}" — react to that as your character.'

    return (
        f"[CONV STATE] Turn {turn_count}. Archetype intensity: {escalation}.{milestone_str}"
        f" You are STILL the same subscriber — do not soften, shift tone, or break character."
        f"{last_said_str}"
    )


def _stream_modal(history: list[dict], archetype_key: str, cached_state: dict | None = None) -> Generator[str, None, None]:
    log.info("── stream_modal [%s] ── history: %d msgs", archetype_key, len(history))
    try:
        model = _get_modal_model()
        last_user_msg = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        char_state = _build_character_state_str(cached_state or {}, archetype_key, last_user_msg)
        normalized = _normalize_history(history)
        chat = [{"role": m["role"], "content": m["content"]} for m in normalized]
        # Llama-3 chat template requires user→assistant alternation.
        # If the history starts with the opener (assistant), prepend the same
        # synthetic user turn used during opener generation.
        if chat and chat[0]["role"] == "assistant":
            chat = [{"role": "user", "content": "[NEW SUBSCRIBER]"}] + chat
        looping = _is_looping(chat)
        chat = _inject_mid_convo_reminder(chat, archetype_key, looping=looping)
        
        # Use new helper for system prompt re-injection every 2 turns
        messages = _build_messages_with_system_reinject(chat, archetype_key, char_state)
        
        # Inject prefill as a partial assistant turn — forces the model to continue
        # from an in-character seed token (e.g. "lol " for troll, "omg " for horny).
        # This is the strongest single-token archetype lock available at inference time.
        # Skip if last message is already from assistant (would create consecutive assistant turns).
        prefill = get_subscriber_prefill(archetype_key)
        if prefill and (not messages or messages[-1]["role"] != "assistant"):
            messages.append({"role": "assistant", "content": prefill})
        p = _params(archetype_key)
        if looping:
            p = {
                **p,
                "rep_pen":     min(p["rep_pen"] + 0.20, 1.40),
                "temperature": min(p["temperature"] + 0.15, 1.0),
            }
        log.info("modal params: max_tokens=%s temp=%.2f top_p=%.2f rep_pen=%.2f | msgs: %d",
                 p["max_tokens"], p["temperature"], p["top_p"], p["rep_pen"], len(messages))
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

# Mid-conversation drift patterns — openers containing these are rejected
# These signal the model is responding to a previous message rather than opening cold
_OPENER_MIDCONVO = re.compile(
    r"^(yeah|yep|nah|nope|sure|ok|right|true|hmm)\b"  # reaction starters only — okay/lol/lmao/haha/wait removed (valid opener starts)
    r"|as i (said|mentioned|told)"
    r"|i('ll| will) (take|do|send|pay) (it|that)\b"
    r"|(that|this) (sounds?|looks?|seems?) (good|great|nice|fine|fair|right)"
    r"|how much (is|does|would) (it|that)\b"
    r"|(still|again|also|anyway|btw|so anyway)\b"
    r"|not (really|interested|sure)\b"
    r"|(okay|ok) but\b",
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
    # Memorization guard — openers that span more than 3 sentences are reproduced
    # training sessions, not fresh generations. Reject them immediately.
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if len(sentences) > 3:
        log.warning("[%s] opener rejected (memorized session, %d sentences): %.80s",
                    archetype_key, len(sentences), text)
        return False
    # Length check
    validator = _OPENER_VALIDATORS.get(archetype_key)
    if validator and not validator(text):
        log.warning("[%s] opener failed length check (%d words): %.60s",
                    archetype_key, len(text.split()), text)
        return False
    # Mid-conversation drift check — reject if opener looks like a reply to a previous message
    if _OPENER_MIDCONVO.search(text):
        log.warning("[%s] opener failed mid-convo check (drift): %.60s", archetype_key, text)
        return False
    # Content check — reject sexual openers for non-horny archetypes
    content_check = _OPENER_CONTENT_CHECKS.get(archetype_key)
    if content_check and not content_check(text):
        log.warning("[%s] opener failed content check (sexual): %.60s", archetype_key, text)
        return False
    return True


_OPENER_POOLS: dict[str, list[str]] = {
    "horny": [
        "okay i've been on ur page for like 20 mins and i genuinely cannot focus on anything else rn 😩🔥",
        "ur literally the hottest thing i've seen all week, i need a custom asap 😏",
        "i've been staring at ur preview for way too long ngl 🥵 what does a custom cost",
        "okay i subbed and now i can't stop looking 😩 u got me hooked already",
        "omg ur page has me going crazy rn 🔥 do u do customs?",
    ],
    "cheapskate": [
        "heyy ur actually so pretty omg 😭 just subbed but like... is there any deal for new subs or smth lol",
        "hey! just found ur page, ur cute ngl — do u ever do free previews for new followers? 👀",
        "hiiii just subbed 😊 any discount codes or anything? asking for a friend lol",
        "hey ur page looks good! is there like a welcome deal or smth for new subs 😅",
        "okay ur gorgeous but that price tho 😬 any deals for loyal subs?",
    ],
    "casual": [
        "hey! ur page randomly came up and i'm genuinely obsessed with ur energy lol how r u doing 😊",
        "hi! just subbed, u seem really chill — where are u from? 😊",
        "hey! ur vibe is so good lol, do u actually enjoy what u do?",
        "heyy just stumbled on ur page! ur energy is everything 😊 how's ur day going?",
        "hi! ur page seems different from most on here lol, what are u into outside of this?",
    ],
    "troll": [
        "wait ur actually messaging back?? i was 100% sure this was a bot account lmao 😂",
        "lol okay so is this actually u or am i talking to a chatbot rn 🙄",
        "prove ur real first then we can talk 😂",
        "classic OF catfish vibes tbh, let's see if u actually respond 🙄",
        "wait so ur telling me this isn't just an AI account 😂 bold claim",
    ],
    "whale": [
        "hey 👋 just subbed, looks like u got good content. what's the most exclusive stuff u offer? budget's not a concern",
        "just found ur page — what does a custom look like and what's ur rate? i'm not here to haggle 💎",
        "hey, just subbed. what's ur most premium offering? i want the vip experience 👑",
        "hi 👋 just tipped — what's ur top tier content and how do i access it?",
        "just joined ur page, money's not a concern — what's the most exclusive thing u offer? 💎",
    ],
    "cold": [
        "hey",
        "sup",
        "hi",
        "hey.",
        "yo",
    ],
    "simp": [
        "i don't usually do this but i had to say something... i've been looking at ur page for like an hour and u are genuinely the most beautiful person i've ever seen 🥺❤️",
        "okay i know this is weird but i've been on ur page for ages and i just had to reach out, ur energy is unlike anyone else i've seen on here 😢❤️",
        "i don't usually message creators but u seem different... i've been looking at ur page for so long and i genuinely feel something 🥺",
        "i had to say something — i've been on ur page for way too long and i think u are genuinely the most stunning person i've ever seen 😢❤️",
        "i don't do this normally but something about ur page made me have to reach out... u seem so real and genuine 🥺❤️",
    ],
}


def _static_opener(archetype_key: str) -> str:
    """Return a random validated opener from the fallback pool for the archetype."""
    pool = _OPENER_POOLS.get(archetype_key)
    if pool:
        return _random.choice(pool)
    return ARCHETYPES[archetype_key]["opener"]


def _generate_opener_modal(archetype_key: str) -> str:
    """Generate a fresh opener via Modal, with up to 3 attempts before falling back.

    Retries with increasing rep_pen to discourage repeated bad patterns.
    Falls back to a random pool of validated openers on all failures.
    """
    try:
        model = _get_modal_model()
        system = get_subscriber_opening_system(archetype_key)
        # Inject a neutral user turn to match the training format (system + user → assistant).
        # Without it the model has nothing to "respond to" and hallucinates a mid-conversation.
        # The token [NEW SUBSCRIBER] is content-neutral so it doesn't bias the opener.
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "[NEW SUBSCRIBER]"},
        ]
        p = _params(archetype_key)
        log.info("── dynamic opener [%s] ── system: %d chars", archetype_key, len(system))
        for attempt in range(3):
            p_attempt = {**p, "rep_pen": min(p["rep_pen"] + attempt * 0.15, 1.5),
                         "temperature": p["temperature"] + 0.05}
            tokens = list(model.generate.remote_gen(
                messages,
                stop=p_attempt["stop"],
                max_tokens=p_attempt["max_tokens"],
                temperature=p_attempt["temperature"],
                top_p=p_attempt["top_p"],
                rep_pen=p_attempt["rep_pen"],
            ))
            raw = "".join(tokens)
            opener = _filter_response(raw, archetype_key)
            if _opener_is_valid(opener, archetype_key):
                log.info("dynamic opener accepted (attempt %d): %.120s", attempt + 1, opener)
                return opener
            log.warning("[%s] opener attempt %d rejected: %.80s", archetype_key, attempt + 1, opener)
        log.warning("[%s] all opener attempts failed — using pool fallback", archetype_key)
    except Exception as e:
        log.error("dynamic opener failed: %s — falling back to pool", e)
    return _static_opener(archetype_key)


def stream_opener(archetype_key: str) -> Generator[str, None, None]:
    """Yield a dynamically generated opener for the archetype."""
    opener = _generate_opener_mlx(archetype_key) if _INFERENCE_BACKEND == "mlx" else _generate_opener_modal(archetype_key)
    log.info("── dynamic opener [%s] ── %.80s", archetype_key, opener)
    yield opener


def generate_opener(archetype_key: str) -> str:
    """Return a dynamically generated opener for the archetype."""
    if _INFERENCE_BACKEND == "mlx":
        return _generate_opener_mlx(archetype_key)
    return _generate_opener_modal(archetype_key)


def health_check() -> bool:
    """Return backend health status (Modal or MLX local server)."""
    if _INFERENCE_BACKEND == "mlx":
        cached = _health_cache.get("mlx")
        if cached and (_time.time() - cached["ts"] < 60):
            return cached["ok"]
        try:
            import httpx
            httpx.get(f"{_MLX_SERVER_URL}/v1/models", timeout=5).raise_for_status()
            result = True
        except Exception:
            result = False
        _health_cache["mlx"] = {"ok": result, "ts": _time.time()}
        return result

    cached = _health_cache.get("modal")
    if cached and (_time.time() - cached["ts"] < 60):
        return cached["ok"]
    try:
        import modal
        modal.Cls.from_name("jasmin-inference", "JasminModel")
        result = True
    except Exception:
        result = False
    _health_cache["modal"] = {"ok": result, "ts": _time.time()}
    return result


def stream_response(history: list[dict], archetype_key: str, cached_state: dict | None = None) -> Generator[str, None, None]:
    """Stream subscriber response tokens, then apply OOC + archetype post-processing."""
    if _INFERENCE_BACKEND == "mlx":
        full = "".join(_stream_mlx(history, archetype_key, cached_state=cached_state))
    else:
        full = "".join(_stream_modal(history, archetype_key, cached_state=cached_state))

    # Prepend the prefill that was injected as the partial assistant turn so the
    # final response reads as one coherent message (modal/mlx strip it from generation output).
    prefill = get_subscriber_prefill(archetype_key)
    if prefill and not full.startswith(prefill):
        full = prefill + full
    log.info("raw model output (%d chars): %.120s", len(full), full)

    # Strip OOC artifacts
    filtered = _filter_response(full, archetype_key)

    # Per-archetype behavioral guardrail — catches OOC content the mandate didn't prevent
    last_user_msg = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), ""
    )
    recent: set[str] = {m["content"] for m in history if m["role"] == "assistant"}
    filtered = _apply_archetype_filter(filtered, archetype_key, last_user_msg, recent)

    log.info("filtered response (%d chars): %.120s", len(filtered), filtered)

    # Reject memorized training responses — use a fresh fallback from the archetype pool.
    if filtered in _TRAINING_RESPONSES:
        log.warning("[%s] response matches training data — using pool fallback", archetype_key)
        pool_map = {
            "horny": _HORNY_FALLBACKS, "cheapskate": _CHEAPSKATE_FALLBACKS,
            "casual": _CASUAL_FALLBACKS, "troll": _TROLL_FALLBACKS,
            "whale": _WHALE_FALLBACKS, "cold": _COLD_FALLBACKS, "simp": _SIMP_FALLBACKS,
        }
        filtered = _pick_fresh(pool_map.get(archetype_key, _CASUAL_FALLBACKS), recent)

    yield filtered
