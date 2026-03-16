"""
Database layer — Supabase when env vars are set, SQLite fallback for local dev.

Required env vars for Supabase:
  SUPABASE_URL   — project URL (https://<ref>.supabase.co)
  SUPABASE_KEY   — anon or service-role key

Supabase table schema (run once in SQL editor):

    CREATE TABLE conversations (
        id         TEXT PRIMARY KEY,
        title      TEXT NOT NULL,
        archetype  TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE messages (
        id              BIGSERIAL PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
        content         TEXT NOT NULL,
        created_at      TEXT NOT NULL
    );
"""

import os
import sys
import uuid
from datetime import datetime, timezone

# Ensure local modules are importable regardless of how this file is loaded
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Backend selection ─────────────────────────────────────────────────────────

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_USE_SUPABASE = bool(_SUPABASE_URL and _SUPABASE_KEY)

if _USE_SUPABASE:
    from supabase import create_client as _create_client
    _sb = _create_client(_SUPABASE_URL, _SUPABASE_KEY)
else:
    # SQLite fallback — used when Supabase env vars are absent (local dev)
    import sqlite3
    import threading
    from pathlib import Path

    _DB_PATH = Path(os.getenv("DB_PATH", "data/chat.db"))
    _lock = threading.Lock()
    _conn: "sqlite3.Connection | None" = None

    def _get_conn() -> "sqlite3.Connection":
        global _conn
        if _conn is None:
            _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
        return _conn


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db() -> None:
    if _USE_SUPABASE:
        return  # tables are managed in the Supabase dashboard
    conn = _get_conn()
    with _lock:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                archetype  TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content         TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );
        """)


# ── Conversation CRUD ─────────────────────────────────────────────────────────

def create_conversation(title: str, archetype: str) -> dict:
    conv_id = uuid.uuid4().hex[:8]
    now = _now()
    row = {"id": conv_id, "title": title, "archetype": archetype, "created_at": now, "updated_at": now}
    if _USE_SUPABASE:
        _sb.table("conversations").insert(row).execute()
    else:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT INTO conversations (id, title, archetype, created_at, updated_at) VALUES (?,?,?,?,?)",
                (conv_id, title, archetype, now, now),
            )
            conn.commit()
    return row


def list_conversations() -> list[dict]:
    if _USE_SUPABASE:
        res = _sb.table("conversations").select("*").order("updated_at", desc=True).execute()
        return res.data or []
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def get_conversation(conv_id: str) -> dict | None:
    if _USE_SUPABASE:
        res = _sb.table("conversations").select("*").eq("id", conv_id).execute()
        return res.data[0] if res.data else None
    conn = _get_conn()
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    return dict(row) if row else None


def update_conversation_title(conv_id: str, title: str) -> None:
    now = _now()
    if _USE_SUPABASE:
        _sb.table("conversations").update({"title": title.strip(), "updated_at": now}).eq("id", conv_id).execute()
    else:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip(), now, conv_id),
            )
            conn.commit()


def get_character_state(conv_id: str) -> dict:
    if _USE_SUPABASE:
        res = _sb.table("conversations").select("character_state").eq("id", conv_id).execute()
        return (res.data[0].get("character_state") or {}) if res.data else {}
    conn = _get_conn()
    row = conn.execute("SELECT character_state FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if row and row["character_state"]:
        import json
        return json.loads(row["character_state"])
    return {}


def update_character_state(conv_id: str, state: dict) -> None:
    import json
    if _USE_SUPABASE:
        _sb.table("conversations").update({"character_state": state}).eq("id", conv_id).execute()
    else:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "UPDATE conversations SET character_state = ? WHERE id = ?",
                (json.dumps(state), conv_id),
            )
            conn.commit()


def delete_conversation(conv_id: str) -> None:
    if _USE_SUPABASE:
        _sb.table("conversations").delete().eq("id", conv_id).execute()
    else:
        conn = _get_conn()
        with _lock:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            conn.commit()


# ── Message CRUD ──────────────────────────────────────────────────────────────

def add_message(conv_id: str, role: str, content: str) -> None:
    now = _now()
    if _USE_SUPABASE:
        _sb.table("messages").insert({
            "conversation_id": conv_id,
            "role": role,
            "content": content,
            "created_at": now,
        }).execute()
        _sb.table("conversations").update({"updated_at": now}).eq("id", conv_id).execute()
    else:
        conn = _get_conn()
        with _lock:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                (conv_id, role, content, now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            conn.commit()


def get_messages(conv_id: str) -> list[dict]:
    if _USE_SUPABASE:
        res = _sb.table("messages").select("*").eq("conversation_id", conv_id).order("id").execute()
        return res.data or []
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_message(msg_id: int) -> None:
    if _USE_SUPABASE:
        _sb.table("messages").delete().eq("id", msg_id).execute()
    else:
        conn = _get_conn()
        with _lock:
            conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
            conn.commit()
