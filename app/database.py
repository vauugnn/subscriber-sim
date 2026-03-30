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

# Check environment variables first
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_USE_SUPABASE = bool(_SUPABASE_URL and _SUPABASE_KEY)

# Supabase client (lazy-loaded to support Streamlit secrets)
_sb = None
_sb_initialized = False

def _get_supabase_client():
    """Lazy-load Supabase client, checking secrets at runtime."""
    global _sb, _sb_initialized, _USE_SUPABASE, _SUPABASE_URL, _SUPABASE_KEY
    
    if _sb_initialized:
        return _sb
    
    _sb_initialized = True
    
    # Try to load from Streamlit secrets if env vars not set
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        try:
            import streamlit as st
            if hasattr(st, 'secrets'):
                _SUPABASE_URL = _SUPABASE_URL or st.secrets.get("SUPABASE_URL", "")
                _SUPABASE_KEY = _SUPABASE_KEY or st.secrets.get("SUPABASE_KEY", "")
                _USE_SUPABASE = bool(_SUPABASE_URL and _SUPABASE_KEY)
        except Exception as e:
            pass
    
    if _USE_SUPABASE and _SUPABASE_URL and _SUPABASE_KEY:
        from supabase import create_client as _create_client
        _sb = _create_client(_SUPABASE_URL, _SUPABASE_KEY)
    elif not _sb:
        raise RuntimeError("Supabase credentials not found. Please configure SUPABASE_URL and SUPABASE_KEY in secrets or environment variables.")
    
    return _sb


# SQLite fallback — used when Supabase not available
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
    # All table creation is managed in Supabase dashboard
    # This function is kept for compatibility but does nothing
    pass


# ── Conversation CRUD ─────────────────────────────────────────────────────────

def create_conversation(title: str, archetype: str) -> dict:
    conv_id = uuid.uuid4().hex[:8]
    now = _now()
    row = {"id": conv_id, "title": title, "archetype": archetype, "created_at": now, "updated_at": now}
    _get_supabase_client().table("conversations").insert(row).execute()
    return row


def list_conversations() -> list[dict]:
    res = _get_supabase_client().table("conversations").select("*").order("updated_at", desc=True).execute()
    return res.data or []


def get_conversation(conv_id: str) -> dict | None:
    res = _get_supabase_client().table("conversations").select("*").eq("id", conv_id).execute()
    return res.data[0] if res.data else None


def update_conversation_title(conv_id: str, title: str) -> None:
    now = _now()
    _get_supabase_client().table("conversations").update({"title": title.strip(), "updated_at": now}).eq("id", conv_id).execute()


def get_character_state(conv_id: str) -> dict:
    res = _get_supabase_client().table("conversations").select("character_state").eq("id", conv_id).execute()
    return (res.data[0].get("character_state") or {}) if res.data else {}


def update_character_state(conv_id: str, state: dict) -> None:
    _get_supabase_client().table("conversations").update({"character_state": state}).eq("id", conv_id).execute()


def delete_conversation(conv_id: str) -> None:
    _get_supabase_client().table("conversations").delete().eq("id", conv_id).execute()


# ── Message CRUD ──────────────────────────────────────────────────────────────

def add_message(conv_id: str, role: str, content: str) -> None:
    now = _now()
    sb = _get_supabase_client()
    sb.table("messages").insert({
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "created_at": now,
    }).execute()
    sb.table("conversations").update({"updated_at": now}).eq("id", conv_id).execute()


def get_messages(conv_id: str) -> list[dict]:
    res = _get_supabase_client().table("messages").select("*").eq("conversation_id", conv_id).order("id").execute()
    return res.data or []


def delete_message(msg_id: int) -> None:
    _get_supabase_client().table("messages").delete().eq("id", msg_id).execute()
