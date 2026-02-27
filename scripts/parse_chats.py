#!/usr/bin/env python3
"""Parse raw OnlyFans chat exports into training JSONL for the Jasmin chatbot.

Reads .txt files from the chatscraper chat data directory and produces
training pairs where subscriber messages = "user" and Jasmin's responses
= "assistant", matching the save_session() schema in subscriber_sim.ipynb.
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────
CHAT_DIR = Path(__file__).resolve().parent.parent / "chat data"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "sessions.jsonl"

# ── File → subscriber label mapping (from manual analysis) ──────────────
LABELED_FILES = {
    "2.txt": "Da",
    "3.txt": "CP",
    "5.txt": "LB",
    "7.txt": "TH",
    "8.txt": "He",
    "10.txt": "Ja",
    "12.txt": "SE",
    "13.txt": "Ga",
    "16.txt": "Za",
    "17.txt": "BB",
}

UNLABELED_FILES = {
    "1.txt", "4.txt", "6.txt", "9.txt", "11.txt",
    "14.txt", "15.txt", "18.txt", "19.txt",
}

SYSTEM_PROMPT = (
    "You are Jasmin (@jizzyjasi), a 19-year-old trans woman from Saudi Arabia "
    "who runs an OnlyFans page. You're flirty, confident, and streetwise about "
    "selling content. You tease subscribers, upsell your videos and photos, use "
    "casual texting style with emojis, and maintain your mysterious identity "
    "behind a hijab. You balance being playful and sexual with being business-savvy."
)

# ── Regex patterns ──────────────────────────────────────────────────────
RE_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}\s*(am|pm)$", re.IGNORECASE)
RE_DATE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}"
    r"(,?\s*'?\d{2,4})?$",
    re.IGNORECASE,
)
RE_DATE_RELATIVE = re.compile(r"^(Yesterday|Today)$", re.IGNORECASE)
RE_PAYMENT = re.compile(r"^\$[\d,.]+\s+(paid|not paid yet)", re.IGNORECASE)
RE_AD_MARKER = re.compile(r"#ad", re.IGNORECASE)
RE_OF_URL = re.compile(r"onlyfans\.com/", re.IGNORECASE)
RE_DURATION = re.compile(r"^-?\d{2}:\d{2}$")

UI_ARTIFACTS = {"Report", "View message", "Pin the message",
                "Drop files to upload", "Send", "|"}

# Jasmin's display names in quote headers
JASMIN_NAMES = {"Jasmin 🖤", "Jasmin", "jizzyjasi"}

# The bio/greeting that appears at the top of most files
BIO_FRAGMENTS = [
    "can't reveal my identity",
    "encouraged by my people",
    "parents don't know",
    "few year visa",
    "dick keeps poking through",
]


# ── Helpers ─────────────────────────────────────────────────────────────

def is_timestamp(line: str) -> bool:
    return bool(RE_TIMESTAMP.match(line.strip()))


def is_date(line: str) -> bool:
    s = line.strip()
    return bool(RE_DATE.match(s) or RE_DATE_RELATIVE.match(s))


def is_payment(line: str) -> bool:
    return bool(RE_PAYMENT.match(line.strip()))


def is_ad_block(line: str) -> bool:
    return bool(RE_AD_MARKER.search(line) and RE_OF_URL.search(line))


def is_ui_artifact(line: str) -> bool:
    return line.strip() in UI_ARTIFACTS


def is_duration_marker(line: str) -> bool:
    return bool(RE_DURATION.match(line.strip()))


def is_bio_line(line: str) -> bool:
    low = line.lower()
    return any(frag in low for frag in BIO_FRAGMENTS)


def is_emoji_only(line: str) -> bool:
    """Check if line contains only emoji/whitespace (reaction counts like '1', '2', '8')."""
    stripped = line.strip()
    if not stripped:
        return True
    if re.match(r"^\d{1,2}$", stripped):
        return False  # Could be a reaction count - handled in quote block
    return False


def parse_date_from_line(line: str) -> datetime | None:
    """Try to extract a date from a date line. Returns datetime or None."""
    s = line.strip()
    if RE_DATE_RELATIVE.match(s):
        return None

    # Try various date formats
    for fmt in [
        "%b %d, '%y", "%b %d, %Y", "%b %d '%y",
        "%b %d, '%y", "%b %d",
    ]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def strip_lines(lines: list[str]) -> list[str]:
    """Remove leading/trailing blank lines from a list of strings."""
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return lines


# ── Line classification ─────────────────────────────────────────────────

def classify_lines(raw_lines: list[str], subscriber_label: str | None):
    """Classify each line and return list of (type, content) tuples.

    Types: 'bio', 'timestamp', 'date', 'payment', 'ad', 'ui',
           'duration', 'subscriber_label', 'quote_start', 'content', 'blank'
    """
    classified = []
    for line in raw_lines:
        stripped = line.strip()

        if not stripped:
            classified.append(("blank", ""))
        elif is_timestamp(stripped):
            classified.append(("timestamp", stripped))
        elif is_date(stripped):
            classified.append(("date", stripped))
        elif is_payment(stripped):
            classified.append(("payment", stripped))
        elif is_ad_block(line):
            classified.append(("ad", stripped))
        elif is_ui_artifact(stripped):
            classified.append(("ui", stripped))
        elif is_duration_marker(stripped):
            classified.append(("duration", stripped))
        elif subscriber_label and stripped == subscriber_label:
            classified.append(("subscriber_label", stripped))
        else:
            classified.append(("content", stripped))

    return classified


# ── Quote block detection ───────────────────────────────────────────────

def detect_quote_blocks(classified: list[tuple[str, str]]) -> set[int]:
    """Find indices that are part of quote blocks and should be skipped.

    Quote pattern (with blanks between each):
      Name (content line - e.g. "Jasmin 🖤", "kareem", "LBM/YD", "Jarrodp")
      , (content line - literal comma)
      Date (date line or content with date-like text)
      " quoted text (content line starting with ")
      [optional: reaction count digit]
      [optional: payment line]
      View message (ui line)
      reply text (content line - KEEP this)

    Also handles inline quotes (no "View message"):
      Name, Date, " quoted text, reply

    We skip everything except the reply line after 'View message'.
    """
    skip_indices = set()

    def next_nonblank(start):
        """Return index of next non-blank line, or None."""
        j = start
        while j < len(classified):
            if classified[j][0] != "blank":
                return j
            j += 1
        return None

    # Scan forward looking for comma content lines as anchors
    i = 0
    while i < len(classified):
        # Anchor: content line that is just ","
        if classified[i][0] == "content" and classified[i][1] == ",":
            comma_idx = i

            # Look backward for the name line (previous non-blank content)
            name_idx = None
            j = i - 1
            while j >= 0:
                if classified[j][0] == "blank":
                    j -= 1
                    continue
                if classified[j][0] == "content":
                    name_idx = j
                break

            if name_idx is None:
                i += 1
                continue

            # Look forward from comma for date line
            date_idx = next_nonblank(comma_idx + 1)
            if date_idx is None:
                i += 1
                continue

            # Date can be classified as "date" or "content" (e.g. "Oct 6, 2025")
            if classified[date_idx][0] not in ("date", "content"):
                i += 1
                continue

            # Look for quoted text line (starts with ")
            quote_idx = next_nonblank(date_idx + 1)
            if quote_idx is None:
                i += 1
                continue

            if classified[quote_idx][0] == "content" and (
                classified[quote_idx][1].startswith('"') or
                classified[quote_idx][1].startswith('\u201c')
            ):
                # Valid quote block found! Mark everything for skipping
                for k in range(name_idx, quote_idx + 1):
                    skip_indices.add(k)
                # Also mark blanks in between
                for k in range(name_idx, quote_idx + 1):
                    skip_indices.add(k)

                # Look forward for reaction count, payment, "View message"
                j = quote_idx + 1
                while j < len(classified):
                    if classified[j][0] == "blank":
                        skip_indices.add(j)
                        j += 1
                        continue
                    if classified[j][0] == "content" and re.match(r"^\d{1,2}$", classified[j][1]):
                        skip_indices.add(j)
                        j += 1
                        continue
                    if classified[j][0] == "payment":
                        skip_indices.add(j)
                        j += 1
                        continue
                    if classified[j][0] == "ui" and classified[j][1] == "View message":
                        skip_indices.add(j)
                        j += 1
                        break
                    break
                # Reply after "View message" is NOT skipped (it's real content)

            elif classified[quote_idx][0] == "content":
                # No quote mark - might be an inline reply to a quoted message
                # without "View message". Check if this looks like a quote header
                # where the "date" line actually contains the quoted text with
                # date prefix like "Feb 15 2:55 pm"
                # Skip only the header (name + comma)
                pass

        i += 1

    return skip_indices


# ── Bio detection ───────────────────────────────────────────────────────

def find_bio_end(classified: list[tuple[str, str]]) -> int:
    """Find the index where the bio/greeting block ends."""
    # Bio is at the very top - look for first timestamp or payment
    for i, (typ, _) in enumerate(classified):
        if typ in ("timestamp", "payment"):
            return i
    return 0


# ── Ad block detection ──────────────────────────────────────────────────

def find_ad_blocks(classified: list[tuple[str, str]]) -> set[int]:
    """Find indices that are part of ad/spam blocks."""
    ad_indices = set()
    i = 0
    while i < len(classified):
        if classified[i][0] == "ad":
            # Mark surrounding content as ad too (ad text often spans multiple lines)
            start = i
            while start > 0 and classified[start - 1][0] in ("content", "blank"):
                # Check if the content before looks like ad text
                if classified[start - 1][0] == "content":
                    content = classified[start - 1][1].lower()
                    if any(kw in content for kw in ["#ad", "onlyfans.com", "sub for free",
                                                      "join her", "find out", "dropped a new"]):
                        start -= 1
                    else:
                        break
                else:
                    start -= 1
            for j in range(start, i + 1):
                ad_indices.add(j)
            i += 1
        else:
            i += 1
    return ad_indices


# ── Labeled file parser ─────────────────────────────────────────────────

def parse_labeled_file(raw_text: str, filename: str, subscriber_label: str) -> list[dict]:
    """Parse a labeled chat file into message sessions."""
    lines = raw_text.split("\n")
    classified = classify_lines(lines, subscriber_label)
    bio_end = find_bio_end(classified)
    quote_skips = detect_quote_blocks(classified)
    ad_skips = find_ad_blocks(classified)

    messages = []  # list of {"role": ..., "content": ..., "date": ...}
    current_speaker = "jasmin"  # default after timestamp
    current_buffer = []
    current_date = None
    last_date = None

    def flush_buffer():
        nonlocal current_buffer
        if current_buffer:
            text = "\n".join(current_buffer).strip()
            if text:
                role = "assistant" if current_speaker == "jasmin" else "user"
                messages.append({
                    "role": role,
                    "content": text,
                    "date": current_date,
                })
            current_buffer = []

    i = bio_end
    while i < len(classified):
        typ, content = classified[i]

        # Skip items
        if i in quote_skips or i in ad_skips:
            i += 1
            continue

        if typ == "blank":
            i += 1
            continue

        if typ == "timestamp":
            flush_buffer()
            current_speaker = "jasmin"  # default after timestamp
            i += 1
            continue

        if typ == "date":
            dt = parse_date_from_line(content)
            if dt:
                current_date = dt
            i += 1
            continue

        if typ == "subscriber_label":
            flush_buffer()
            current_speaker = "subscriber"
            i += 1
            continue

        if typ in ("payment", "ui", "duration", "ad"):
            i += 1
            continue

        if typ == "content":
            # Check for ad content in regular content lines
            if is_ad_block(content):
                i += 1
                continue
            current_buffer.append(content)
            i += 1
            continue

        i += 1

    flush_buffer()

    return split_into_sessions(messages, filename, "labeled")


# ── Unlabeled file parser ───────────────────────────────────────────────

def parse_unlabeled_file(raw_text: str, filename: str) -> list[dict]:
    """Parse an unlabeled chat file using alternating speaker heuristic."""
    lines = raw_text.split("\n")
    classified = classify_lines(lines, subscriber_label=None)
    bio_end = find_bio_end(classified)
    quote_skips = detect_quote_blocks(classified)
    ad_skips = find_ad_blocks(classified)

    messages = []
    # After bio, first speaker at first timestamp is subscriber (they messaged first)
    # Then alternate at each timestamp boundary
    current_speaker = "subscriber"  # first message after bio is subscriber
    current_buffer = []
    current_date = None
    timestamp_count = 0

    def flush_buffer():
        nonlocal current_buffer
        if current_buffer:
            text = "\n".join(current_buffer).strip()
            if text:
                role = "assistant" if current_speaker == "jasmin" else "user"
                messages.append({
                    "role": role,
                    "content": text,
                    "date": current_date,
                })
            current_buffer = []

    i = bio_end
    while i < len(classified):
        typ, content = classified[i]

        if i in quote_skips or i in ad_skips:
            i += 1
            continue

        if typ == "blank":
            i += 1
            continue

        if typ == "timestamp":
            flush_buffer()
            timestamp_count += 1
            # Alternate speakers: odd timestamps = subscriber, even = jasmin
            # (first timestamp after bio is subscriber's message)
            if timestamp_count % 2 == 1:
                current_speaker = "subscriber"
            else:
                current_speaker = "jasmin"
            i += 1
            continue

        if typ == "date":
            dt = parse_date_from_line(content)
            if dt:
                current_date = dt
            i += 1
            continue

        if typ in ("payment", "ui", "duration", "ad"):
            i += 1
            continue

        if typ == "content":
            if is_ad_block(content):
                i += 1
                continue
            current_buffer.append(content)
            i += 1
            continue

        i += 1

    flush_buffer()

    return split_into_sessions(messages, filename, "heuristic")


# ── Session splitting ───────────────────────────────────────────────────

def split_into_sessions(
    messages: list[dict],
    source_file: str,
    confidence: str,
) -> list[dict]:
    """Split messages into sessions based on gaps and content breaks."""
    if not messages:
        return []

    # Filter out noise
    messages = filter_noise(messages)

    if len(messages) < 3:
        return []

    # For now treat the whole conversation as one session, then split on
    # 7+ day date gaps if we have date info
    sessions = []
    current_session = []

    for msg in messages:
        current_session.append(msg)

    # Check for date-based splits
    if any(m.get("date") for m in current_session):
        split_sessions = split_on_date_gaps(current_session)
    else:
        split_sessions = [current_session]

    # Cap at 100 turns per session, drop sessions < 3 turns
    final_sessions = []
    for sess in split_sessions:
        # Split into chunks of 100 turns
        chunks = [sess[i:i + 100] for i in range(0, len(sess), 100)]
        for chunk in chunks:
            if len(chunk) >= 3:
                final_sessions.append(chunk)

    # Build output records
    for sess_messages in final_sessions:
        # Ensure proper role alternation - merge consecutive same-role messages
        merged = merge_consecutive_roles(sess_messages)
        if len(merged) < 3:
            continue

        record = build_session_record(merged, source_file, confidence)
        if record:
            sessions.append(record)

    return sessions


def split_on_date_gaps(messages: list[dict]) -> list[list[dict]]:
    """Split message list on 7+ day date gaps."""
    sessions = []
    current = [messages[0]]

    for i in range(1, len(messages)):
        prev_date = None
        curr_date = messages[i].get("date")

        # Find most recent date in current session
        for m in reversed(current):
            if m.get("date"):
                prev_date = m["date"]
                break

        if prev_date and curr_date:
            gap = abs((curr_date - prev_date).days)
            if gap >= 7:
                sessions.append(current)
                current = []

        current.append(messages[i])

    if current:
        sessions.append(current)

    return sessions


def merge_consecutive_roles(messages: list[dict]) -> list[dict]:
    """Merge consecutive messages from the same role into one message."""
    if not messages:
        return []

    merged = [{"role": messages[0]["role"], "content": messages[0]["content"]}]

    for msg in messages[1:]:
        if msg["role"] == merged[-1]["role"]:
            merged[-1]["content"] += "\n" + msg["content"]
        else:
            merged.append({"role": msg["role"], "content": msg["content"]})

    return merged


def filter_noise(messages: list[dict]) -> list[dict]:
    """Remove noisy messages: ads, broadcasts, UI artifacts."""
    filtered = []
    for msg in messages:
        content = msg["content"].strip()

        # Skip empty
        if not content:
            continue

        # Skip ads that slipped through
        if "#ad" in content.lower() and "onlyfans.com" in content.lower():
            continue

        # Skip UI artifacts
        if content in UI_ARTIFACTS:
            continue

        # Skip pure reaction counts
        if re.match(r"^\d{1,2}$", content):
            continue

        # Skip duration markers
        if RE_DURATION.match(content):
            continue

        filtered.append(msg)

    # Detect broadcast runs: 3+ consecutive jasmin messages across the list
    # that look like mass messages (repetitive/templated)
    final = []
    i = 0
    while i < len(filtered):
        run_start = i
        if filtered[i]["role"] == "assistant":
            run_end = i
            while run_end + 1 < len(filtered) and filtered[run_end + 1]["role"] == "assistant":
                run_end += 1
            run_length = run_end - run_start + 1
            if run_length >= 3:
                # Skip entire broadcast run
                i = run_end + 1
                continue
        final.append(filtered[i])
        i += 1

    return final


def build_session_record(messages: list[dict], source_file: str, confidence: str) -> dict | None:
    """Build a session record in the save_session() format."""
    # Strip date keys from messages
    clean_messages = []
    for msg in messages:
        clean_messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # Prepend system prompt
    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ] + clean_messages

    # Ensure first non-system message is "user" (subscriber)
    if len(full_messages) > 1 and full_messages[1]["role"] != "user":
        # Trim leading assistant messages
        while len(full_messages) > 1 and full_messages[1]["role"] != "user":
            full_messages.pop(1)

    if len(full_messages) < 4:  # system + at least 3 conversation messages
        return None

    # Count turns (user messages = subscriber turns)
    turns = len([m for m in full_messages if m["role"] == "user"])

    return {
        "messages": full_messages,
        "archetype": "real_data",
        "turns": turns,
        "session_id": str(uuid.uuid4())[:8],
        "source_file": source_file,
        "source_confidence": confidence,
    }


# ── Validation ──────────────────────────────────────────────────────────

def validate_session(session: dict) -> list[str]:
    """Validate a session record and return list of issues."""
    issues = []

    # Check required keys
    for key in ("messages", "archetype", "turns", "session_id"):
        if key not in session:
            issues.append(f"Missing key: {key}")

    msgs = session.get("messages", [])

    # Check system prompt
    if not msgs or msgs[0]["role"] != "system":
        issues.append("First message should be system prompt")

    # Check for 5+ consecutive same-role messages
    consecutive = 1
    for i in range(2, len(msgs)):
        if msgs[i]["role"] == msgs[i - 1]["role"]:
            consecutive += 1
            if consecutive >= 5:
                issues.append(f"5+ consecutive {msgs[i]['role']} messages at index {i}")
                break
        else:
            consecutive = 1

    # Check for ad content leakage
    for msg in msgs:
        content = msg.get("content", "").lower()
        if "#ad" in content and "onlyfans.com" in content:
            issues.append(f"Ad content leaked into {msg['role']} message")
            break

    # Check for UI artifact leakage
    for msg in msgs[1:]:  # skip system
        if msg["content"].strip() in UI_ARTIFACTS:
            issues.append(f"UI artifact in {msg['role']} message: {msg['content']}")

    return issues


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Chat Parser: Raw Exports → Training JSONL")
    print("=" * 60)
    print(f"Input:  {CHAT_DIR}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    if not CHAT_DIR.exists():
        print(f"ERROR: Chat directory not found: {CHAT_DIR}")
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    all_sessions = []
    stats = {
        "files_processed": 0,
        "files_skipped": 0,
        "sessions_generated": 0,
        "total_turns": 0,
        "labeled_sessions": 0,
        "heuristic_sessions": 0,
        "validation_issues": 0,
    }

    # Process all txt files
    for txt_file in sorted(CHAT_DIR.glob("*.txt"), key=lambda f: int(f.stem)):
        filename = txt_file.name
        print(f"Processing {filename}...", end=" ")

        try:
            raw_text = txt_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"ERROR reading: {e}")
            stats["files_skipped"] += 1
            continue

        if filename in LABELED_FILES:
            label = LABELED_FILES[filename]
            sessions = parse_labeled_file(raw_text, filename, label)
            for s in sessions:
                s["source_confidence"] = "labeled"
        elif filename in UNLABELED_FILES:
            sessions = parse_unlabeled_file(raw_text, filename)
        else:
            print(f"SKIP (unknown file)")
            stats["files_skipped"] += 1
            continue

        # Validate
        valid_sessions = []
        for sess in sessions:
            issues = validate_session(sess)
            if issues:
                stats["validation_issues"] += len(issues)
                for issue in issues:
                    print(f"\n  WARN: {issue}", end="")
            valid_sessions.append(sess)

        turns_in_file = sum(s["turns"] for s in valid_sessions)
        labeled_count = sum(1 for s in valid_sessions if s.get("source_confidence") == "labeled")
        heuristic_count = sum(1 for s in valid_sessions if s.get("source_confidence") == "heuristic")

        print(f"{len(valid_sessions)} sessions, {turns_in_file} turns")

        all_sessions.extend(valid_sessions)
        stats["files_processed"] += 1
        stats["sessions_generated"] += len(valid_sessions)
        stats["total_turns"] += turns_in_file
        stats["labeled_sessions"] += labeled_count
        stats["heuristic_sessions"] += heuristic_count

    # Write output
    print()
    print(f"Writing {len(all_sessions)} sessions to {OUTPUT_FILE}...")

    with open(OUTPUT_FILE, "w") as f:
        for session in all_sessions:
            f.write(json.dumps(session, ensure_ascii=False) + "\n")

    # Print stats
    print()
    print("=" * 60)
    print("STATISTICS")
    print("=" * 60)
    print(f"  Files processed:     {stats['files_processed']}")
    print(f"  Files skipped:       {stats['files_skipped']}")
    print(f"  Sessions generated:  {stats['sessions_generated']}")
    print(f"  Total turns:         {stats['total_turns']}")
    print(f"  Labeled sessions:    {stats['labeled_sessions']}")
    print(f"  Heuristic sessions:  {stats['heuristic_sessions']}")
    print(f"  Validation issues:   {stats['validation_issues']}")
    print()

    # Spot-check: print sample sessions
    print("=" * 60)
    print("SPOT CHECK (first 3 sessions)")
    print("=" * 60)
    for i, sess in enumerate(all_sessions[:3]):
        print(f"\n--- Session {i+1}: {sess['source_file']} "
              f"({sess['source_confidence']}, {sess['turns']} turns) ---")
        for msg in sess["messages"][:8]:  # show first 8 messages
            role = msg["role"]
            content = msg["content"][:120]
            if len(msg["content"]) > 120:
                content += "..."
            print(f"  [{role:9s}] {content}")
        if len(sess["messages"]) > 8:
            print(f"  ... ({len(sess['messages']) - 8} more messages)")
    print()


if __name__ == "__main__":
    main()
