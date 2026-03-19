import sys
import os

# Ensure local modules are importable both in Docker (PYTHONPATH=/app) and natively
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from datetime import datetime

import database as db
import inference
from archetypes import ARCHETYPES


# ── Export conversation as text ────────────────────────────────────────────────
def export_conversation_as_text(messages: list[dict], conv_title: str) -> str:
    """Format conversation messages with role tags for download."""
    lines = [f"# {conv_title}\n"]
    for msg in messages:
        role = "Subscriber" if msg["role"] == "assistant" else "Jasmin"
        lines.append(f"[{role}]")
        lines.append(msg["content"])
        lines.append("")
    return "\n".join(lines)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Jasmin Chat Sim",
    page_icon=":material/chat:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,1,0">
<style>
    /* Sidebar */
    div[data-testid="stSidebarContent"] { padding: 12px 10px !important; }
    div[data-testid="stSidebar"] hr { margin: 8px 0 !important; opacity: 0.25 !important; }

    /* Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        box-shadow: 0 2px 8px rgba(0,0,0,0.10), 0 1px 3px rgba(0,0,0,0.06) !important;
        border-radius: 14px !important;
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 8px 24px rgba(0,0,0,0.14), 0 2px 6px rgba(0,0,0,0.08) !important;
        transform: translateY(-2px);
    }

    /* Equal-height picker cards */
    div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stButton"]) { min-height: 270px; }
    div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stButton"]) > div[data-testid="stVerticalBlock"] {
        display: flex; flex-direction: column; min-height: 248px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stButton"]) > div[data-testid="stVerticalBlock"] > div:last-child {
        margin-top: auto; padding-top: 8px;
    }

    /* Chat messages */
    .stChatMessage { border-radius: 12px; margin-bottom: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }

    /* Icon badge */
    .arch-badge { display:flex; align-items:center; gap:12px; margin-bottom:6px; }
    .arch-badge-icon {
        width:46px; height:46px; border-radius:13px;
        display:flex; align-items:center; justify-content:center;
        flex-shrink:0; box-shadow: 0 3px 10px rgba(0,0,0,0.25);
    }
    .arch-badge-icon .material-symbols-rounded { font-size:26px; color:white; line-height:1; }
    .arch-badge-label { font-weight:700; font-size:1rem; line-height:1.3; }

    /* Typing indicator */
    .typing-indicator { display:flex; gap:5px; align-items:center; padding:6px 2px; }
    .typing-indicator span {
        width:9px; height:9px; border-radius:50%;
        background:currentColor; opacity:0.35;
        animation: typing-bounce 1.1s infinite ease-in-out;
    }
    .typing-indicator span:nth-child(2) { animation-delay:0.18s; }
    .typing-indicator span:nth-child(3) { animation-delay:0.36s; }
    @keyframes typing-bounce {
        0%,60%,100% { transform:translateY(0); opacity:0.35; }
        30% { transform:translateY(-7px); opacity:0.9; }
    }

    /* Archetype pill in chat header */
    .arch-pill {
        display:inline-flex; align-items:center; gap:6px;
        padding:3px 10px 3px 6px; border-radius:20px;
        border:1px solid rgba(128,128,128,0.22);
        font-size:0.78rem; font-weight:500; line-height:1.8;
    }
    .arch-pill-dot { width:10px; height:10px; border-radius:3px; flex-shrink:0; }

    /* Status */
    .server-ok  { color:#22c55e; font-weight:600; font-size:0.8rem; }
    .server-err { color:#ef4444; font-weight:600; font-size:0.8rem; }
    .backend-badge { font-size:0.72rem; color:#94a3b8; font-weight:500; letter-spacing:0.03em; }
</style>
""", unsafe_allow_html=True)

# ── DB init ───────────────────────────────────────────────────────────────────
db.init_db()

# ── Session state (restore from URL on first load) ────────────────────────────
if "active_conv_id" not in st.session_state:
    _url_conv = st.query_params.get("conv")
    # Conv IDs are hex strings — store as-is, never cast to int
    st.session_state.active_conv_id = _url_conv if _url_conv else None
if "show_new_conv" not in st.session_state:
    st.session_state.show_new_conv = st.query_params.get("view") == "new"
if "editing_title" not in st.session_state:
    st.session_state.editing_title = None
if "pending_opener" not in st.session_state:
    st.session_state.pending_opener = None

# ── Handle archetype picker click (query param set by HTML grid) ──────────────
_pick = st.query_params.get("pick")
if _pick and _pick in ARCHETYPES:
    # Clear all state before creating new conversation to prevent any bleed
    st.session_state.active_conv_id = None
    st.session_state.show_new_conv = False
    st.session_state.editing_title = None
    st.query_params.clear()
    _arch_p = ARCHETYPES[_pick]
    _title_p = f"{_arch_p['label']} · {datetime.now().strftime('%b %d %H:%M')}"
    _conv_p = db.create_conversation(_title_p, _pick)
    st.session_state.active_conv_id = _conv_p["id"]
    st.session_state.pending_opener = _pick
    st.rerun()

# ── Sync URL to current state ─────────────────────────────────────────────────
if st.session_state.active_conv_id:
    st.query_params["conv"] = str(st.session_state.active_conv_id)
elif st.session_state.show_new_conv:
    st.query_params["view"] = "new"
else:
    st.query_params.clear()

# ── Helpers ───────────────────────────────────────────────────────────────────
def _short(text: str, n: int = 26) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _ts() -> str:
    return datetime.now().strftime("%b %d %H:%M")


def _arch_badge(arch: dict) -> None:
    """Render an icon badge + label header for an archetype card."""
    st.markdown(f"""
    <div class="arch-badge">
        <div class="arch-badge-icon"
             style="background:linear-gradient(135deg,{arch['gradient']});">
            <span class="material-symbols-rounded">{arch['icon']}</span>
        </div>
        <span class="arch-badge-label">{arch['label']}</span>
    </div>
    """, unsafe_allow_html=True)


def _arch_grid_html() -> str:
    """Build a self-contained HTML/CSS grid of archetype cards.
    All styles are inline so they work inside st.html()'s isolated iframe."""
    cards = ""
    for key, arch in ARCHETYPES.items():
        cards += f"""
        <div class="card">
            <div class="badge">
                <div class="icon" style="background:linear-gradient(135deg,{arch['gradient']});">
                    <span class="material-symbols-rounded">{arch['icon']}</span>
                </div>
                <span class="name">{arch['label']}</span>
            </div>
            <div class="desc">{arch['description']}</div>
            <div class="opener">&ldquo;{arch['opener']}&rdquo;</div>
            <a class="btn" href="?pick={key}">&#8594;&nbsp; Start chat</a>
        </div>"""
    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,1,0">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: transparent; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    padding: 4px 2px 8px;
    align-items: stretch;
  }}
  .card {{
    display: flex;
    flex-direction: column;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 14px;
    padding: 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    transition: box-shadow .2s, transform .2s;
  }}
  .card:hover {{
    box-shadow: 0 8px 24px rgba(0,0,0,0.35);
    transform: translateY(-2px);
  }}
  .badge {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }}
  .icon {{
    width: 46px; height: 46px;
    border-radius: 13px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 3px 10px rgba(0,0,0,0.3);
  }}
  .material-symbols-rounded {{ font-size: 26px; color: white; line-height: 1; }}
  .name {{ font-weight: 700; font-size: 1rem; color: #fff; }}
  .desc {{
    font-size: 0.82rem;
    color: rgba(255,255,255,0.6);
    line-height: 1.45;
    margin-bottom: 10px;
    flex-grow: 1;
  }}
  .opener {{
    font-size: 0.82rem;
    font-style: italic;
    color: rgba(255,255,255,0.5);
    line-height: 1.4;
    margin-bottom: 16px;
    flex-grow: 1;
  }}
  .btn {{
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 9px 0;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.15);
    background: transparent;
    color: rgba(255,255,255,0.85);
    font-size: 0.88rem;
    text-decoration: none;
    margin-top: auto;
    transition: background .15s;
  }}
  .btn:hover {{ background: rgba(255,255,255,0.1); color: #fff; text-decoration: none; }}
</style>
<div class="grid">{cards}</div>
"""


def _start_new_conv(archetype_key: str) -> None:
    # Reset all state before creating new conversation
    st.session_state.active_conv_id = None
    st.session_state.show_new_conv = False
    st.session_state.editing_title = None
    arch = ARCHETYPES[archetype_key]
    title = f"{arch['label']} · {_ts()}"
    conv = db.create_conversation(title, archetype_key)
    st.session_state.active_conv_id = conv["id"]
    st.session_state.pending_opener = archetype_key


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    col_h, col_s = st.columns([3, 1])
    with col_h:
        st.markdown("#### Jasmin Sim")
    with col_s:
        healthy = inference.health_check()
        status_cls = "server-ok" if healthy else "server-err"
        status_txt = "● On" if healthy else "● Off"
        backend_label = "MLX" if inference._INFERENCE_BACKEND == "mlx" else "Modal"
        st.markdown(
            f'<span class="{status_cls}">{status_txt}</span>'
            f'<br><span class="backend-badge">{backend_label}</span>',
            unsafe_allow_html=True,
        )

    if st.button("New Conversation", icon=":material/add:", use_container_width=True, type="primary"):
        st.session_state.show_new_conv = True
        st.session_state.active_conv_id = None
        st.session_state.editing_title = None
        st.rerun()

    st.caption("Conversations")

    conversations = db.list_conversations()
    if not conversations:
        st.caption("No conversations yet.")

    for conv in conversations:
        conv_id = conv["id"]

        if st.session_state.editing_title == conv_id:
            new_title = st.text_input(
                "Rename",
                value=conv["title"],
                key=f"ti_{conv_id}",
                label_visibility="collapsed",
            )
            c1, c2 = st.columns(2)
            if c1.button("Save", icon=":material/check:", key=f"save_{conv_id}", use_container_width=True):
                if new_title.strip():
                    db.update_conversation_title(conv_id, new_title.strip())
                st.session_state.editing_title = None
                st.rerun()
            if c2.button("Cancel", icon=":material/close:", key=f"cancel_{conv_id}", use_container_width=True):
                st.session_state.editing_title = None
                st.rerun()
        else:
            is_active = st.session_state.active_conv_id == conv_id
            label = f"{'**' if is_active else ''}{_short(conv['title'])}{'**' if is_active else ''}"
            c1, c2, c3 = st.columns([5, 1, 1])
            with c1:
                if st.button(label, key=f"cv_{conv_id}", use_container_width=True):
                    st.session_state.active_conv_id = conv_id
                    st.session_state.show_new_conv = False
                    st.session_state.editing_title = None
                    st.rerun()
            with c2:
                if st.button("", icon=":material/edit:", key=f"ed_{conv_id}", help="Rename"):
                    st.session_state.editing_title = conv_id
                    st.rerun()
            with c3:
                if st.button("", icon=":material/delete:", key=f"dl_{conv_id}", help="Delete"):
                    db.delete_conversation(conv_id)
                    if st.session_state.active_conv_id == conv_id:
                        st.session_state.active_conv_id = None
                    st.rerun()


# ── Main area ─────────────────────────────────────────────────────────────────

# ── New conversation: archetype picker ───────────────────────────────────────
if st.session_state.show_new_conv:
    st.markdown("## New Conversation")
    st.markdown("Choose a subscriber type — you'll play Jasmin responding to them:")
    st.html(_arch_grid_html())

# ── Active conversation: chat view ───────────────────────────────────────────
elif st.session_state.active_conv_id:
    conv = db.get_conversation(st.session_state.active_conv_id)

    if not conv:
        st.warning("Conversation not found.")
        st.session_state.active_conv_id = None
        st.session_state.editing_title = None
        st.rerun()

    # Paranoia check: conv ID in DB must match session state exactly
    if conv and conv["id"] != st.session_state.active_conv_id:
        st.session_state.active_conv_id = None
        st.rerun()

    arch = ARCHETYPES.get(conv["archetype"], ARCHETYPES["casual"])

    # Load messages once
    messages = db.get_messages(st.session_state.active_conv_id)

    # Header with export button
    col_title, col_export = st.columns([5, 1])
    with col_title:
        arch_dot = f'<span class="arch-pill-dot" style="background:linear-gradient(135deg,{arch["gradient"]});"></span>'
        arch_pill = f'<span class="arch-pill">{arch_dot} {arch["label"]}</span>'
        st.markdown(f"**{conv['title']}** &nbsp; {arch_pill}", unsafe_allow_html=True)

    with col_export:
        if messages:
            export_text = export_conversation_as_text(messages, conv["title"])
            st.download_button(
                label="📥 Export",
                data=export_text,
                file_name=f"{conv['title'].replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    st.markdown("---")

    # Chat history — assistant = subscriber (model), user = Jasmin (you)
    for msg in messages:
        role = msg["role"]
        if role == "assistant":
            with st.chat_message("assistant", avatar=f":material/{arch['icon']}:"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("user", avatar=":material/face_5:"):
                st.markdown(msg["content"])

    # Stream dynamic opener for newly created conversations
    if st.session_state.get("pending_opener"):
        _opener_arch = st.session_state.pending_opener
        st.session_state.pending_opener = None
        with st.chat_message("assistant", avatar=f":material/{arch['icon']}:"):
            placeholder = st.empty()
            placeholder.markdown(
                '<div class="typing-indicator"><span></span><span></span><span></span></div>',
                unsafe_allow_html=True,
            )
            full_opener = ""
            try:
                for chunk in inference.stream_opener(_opener_arch):
                    if not full_opener:
                        placeholder.empty()
                    full_opener += chunk
                    placeholder.markdown(full_opener + " ▌")
            except Exception:
                full_opener = inference.generate_opener(_opener_arch)
            if not full_opener or not full_opener.strip():
                full_opener = inference.generate_opener(_opener_arch)
            placeholder.markdown(full_opener)
        db.add_message(st.session_state.active_conv_id, "assistant", full_opener)
        st.rerun()

    # Input — user types as Jasmin
    prompt = st.chat_input("Reply as Jasmin…")
    if prompt:
        db.add_message(st.session_state.active_conv_id, "user", prompt)

        with st.chat_message("user", avatar=":material/face_5:"):
            st.markdown(prompt)

        updated_history = db.get_messages(st.session_state.active_conv_id)
        history_for_model = [{"role": m["role"], "content": m["content"]} for m in updated_history]
        cached_state = db.get_character_state(st.session_state.active_conv_id)

        with st.chat_message("assistant", avatar=f":material/{arch['icon']}:"):
            placeholder = st.empty()
            placeholder.markdown(
                '<div class="typing-indicator"><span></span><span></span><span></span></div>',
                unsafe_allow_html=True,
            )
            full_response = ""
            for chunk in inference.stream_response(history_for_model, conv["archetype"], cached_state=cached_state):
                if not full_response:
                    placeholder.empty()
                full_response += chunk
                placeholder.markdown(full_response + " ▌")
            placeholder.markdown(full_response)

        db.add_message(st.session_state.active_conv_id, "assistant", full_response)
        new_state = inference.update_character_state(cached_state, full_response, conv["archetype"])
        db.update_character_state(st.session_state.active_conv_id, new_state)
        st.rerun()

# ── Welcome screen ────────────────────────────────────────────────────────────
else:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("## Jasmin Chat Sim")
    st.markdown("Practice responding as Jasmin. Pick a subscriber type to start.")
    st.html(_arch_grid_html())
