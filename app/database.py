import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/chat.db"))

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Conversation CRUD ─────────────────────────────────────────────────────────

def create_conversation(title: str, archetype: str) -> dict:
    conn = _get_conn()
    conv_id = uuid.uuid4().hex[:8]
    now = _now()
    with _lock:
        conn.execute(
            "INSERT INTO conversations (id, title, archetype, created_at, updated_at) VALUES (?,?,?,?,?)",
            (conv_id, title, archetype, now, now),
        )
        conn.commit()
    return {"id": conv_id, "title": title, "archetype": archetype, "created_at": now, "updated_at": now}


def list_conversations() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conv_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    return dict(row) if row else None


def update_conversation_title(conv_id: str, title: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title.strip(), _now(), conv_id),
        )
        conn.commit()


def delete_conversation(conv_id: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()


# ── Message CRUD ──────────────────────────────────────────────────────────────

def add_message(conv_id: str, role: str, content: str) -> None:
    conn = _get_conn()
    now = _now()
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
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_message(msg_id: int) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
        conn.commit()
