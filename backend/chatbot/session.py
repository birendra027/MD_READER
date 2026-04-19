"""
chatbot/session.py
In-memory session store keyed by session ID with TTL cleanup.
Persists session memory to disk so returning users get continuity.
"""
from __future__ import annotations
import asyncio
import json
import shutil
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from chatbot.models import SessionState, Turn
from chatbot.config import SESSION_TTL_MINUTES
import s3_client

logger = logging.getLogger(__name__)

_sessions: dict[str, SessionState] = {}
_lock = asyncio.Lock()

# ── Persistent memory on disk ────────────────────────────────────
_MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
_MEMORY_DIR.mkdir(exist_ok=True)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _memory_path(session_id: str) -> Path:
    """Return the JSON file path for a given session."""
    # Sanitise session_id to prevent path traversal
    safe = session_id.replace("/", "_").replace("\\", "_").replace("..", "_")
    return _MEMORY_DIR / f"{safe}.json"


def _save_session_sync(session: SessionState) -> None:
    """Persist a single session to disk and to S3 (blocking — run in executor)."""
    data = {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "last_active": session.last_active.isoformat(),
        "history": [{"role": t.role, "content": t.content} for t in session.history],
        "execution_contexts": session.execution_contexts,
    }
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    # ── local disk ────────────────────────────────────────────────
    path = _memory_path(session.session_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    # ── S3 ────────────────────────────────────────────────────────
    try:
        key = s3_client._memory_key(session.session_id)
        s3_client.upload_bytes(key, payload.encode("utf-8"), content_type="application/json")
    except Exception:
        logger.warning("S3 session persist failed for %s", session.session_id[:8])


def _load_session_sync(session_id: str) -> SessionState | None:
    """Load a session from disk (blocking — run in executor)."""
    path = _memory_path(session_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        history = [Turn(role=t["role"], content=t["content"]) for t in raw.get("history", [])]
        return SessionState(
            session_id=raw["session_id"],
            history=history,
            execution_contexts=raw.get("execution_contexts", []),
            created_at=datetime.fromisoformat(raw["created_at"]),
            last_active=datetime.fromisoformat(raw["last_active"]),
        )
    except Exception:
        logger.exception("Failed to load session from %s", path)
        return None


def _delete_memory_sync(session_id: str) -> None:
    """Remove persisted session file from disk and all S3 objects for the session."""
    path = _memory_path(session_id)
    path.unlink(missing_ok=True)
    try:
        s3_client.delete_session(session_id)
    except Exception:
        logger.warning("S3 delete_session failed for %s", session_id[:8])


async def get_or_create(session_id: str | None) -> SessionState:
    """Return an existing session or create a new one.
    If session is not in memory but exists on disk, restore it."""
    async with _lock:
        if session_id and session_id in _sessions:
            session = _sessions[session_id]
            session.last_active = datetime.now(timezone.utc)
            return session

        # Try restoring from disk
        if session_id:
            loop = asyncio.get_event_loop()
            restored = await loop.run_in_executor(None, _load_session_sync, session_id)
            if restored:
                restored.last_active = datetime.now(timezone.utc)
                _sessions[session_id] = restored
                logger.info("Restored session %s from disk (%d turns)", session_id[:8], len(restored.history))
                return restored

        new_id = session_id or str(uuid.uuid4())
        session = SessionState(session_id=new_id)
        _sessions[new_id] = session
        return session


async def append_turn(session_id: str, role: str, content: str) -> None:
    """Add a turn to the session history and persist to disk."""
    async with _lock:
        session = _sessions.get(session_id)
        if session:
            session.history.append(Turn(role=role, content=content))
            session.last_active = datetime.now(timezone.utc)
            # Persist after every turn so data survives crashes
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _save_session_sync, session)


async def append_execution_context(session_id: str, content: str, max_items: int = 8) -> None:
    """Persist hidden execution context for later follow-up questions.

    This is intentionally stored separately from chat history so runtime
    output/errors can inform later answers without becoming normal visible
    chat messages.
    """
    if not content.strip():
        return
    async with _lock:
        session = _sessions.get(session_id)
        if not session:
            return
        session.execution_contexts.append(content)
        if len(session.execution_contexts) > max_items:
            session.execution_contexts = session.execution_contexts[-max_items:]
        session.last_active = datetime.now(timezone.utc)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _save_session_sync, session)


async def get_history(session_id: str) -> list[dict]:
    """Return the session history as a list of dicts."""
    async with _lock:
        session = _sessions.get(session_id)
        if not session:
            return []
        return [{"role": t.role, "content": t.content} for t in session.history]


async def get_session_summary(session_id: str) -> str | None:
    """Build a compact summary of past interactions for the LLM context.
    Returns None if there's no prior memory."""
    async with _lock:
        session = _sessions.get(session_id)

    if not session or not session.history:
        # Check disk
        loop = asyncio.get_event_loop()
        restored = await loop.run_in_executor(None, _load_session_sync, session_id)
        if not restored or not restored.history:
            return None
        session = restored

    # Build a compact digest of past topics
    user_msgs = [t.content for t in session.history if t.role == "user"]
    if not user_msgs:
        return None

    # Keep the last 10 user messages as context hints
    recent = user_msgs[-10:]
    summary = (
        f"This user has interacted before (session {session.session_id[:8]}). "
        f"Previous topics/queries:\n"
    )
    for i, msg in enumerate(recent, 1):
        # Truncate long messages
        short = msg[:200] + "…" if len(msg) > 200 else msg
        summary += f"  {i}. {short}\n"
    summary += (
        f"\nTotal prior turns: {len(session.history)}. "
        f"First interaction: {session.created_at.strftime('%Y-%m-%d %H:%M')} UTC.\n"
        "Maintain continuity — reference earlier context where relevant."
    )
    return summary


async def clear_session(session_id: str) -> None:
    """Remove a session from memory and disk."""
    async with _lock:
        _sessions.pop(session_id, None)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _delete_memory_sync, session_id)


async def save_all_sessions() -> int:
    """Persist every active session to disk. Returns count saved."""
    async with _lock:
        sessions = list(_sessions.values())
    loop = asyncio.get_event_loop()
    count = 0
    for s in sessions:
        if s.history:  # Only save sessions with actual content
            await loop.run_in_executor(None, _save_session_sync, s)
            count += 1
    logger.info("Saved %d session(s) to disk", count)
    return count


def cleanup_output_dir() -> int:
    """Delete all files in the output directory. Returns count deleted."""
    count = 0
    if _OUTPUT_DIR.is_dir():
        for p in _OUTPUT_DIR.iterdir():
            try:
                if p.is_file():
                    p.unlink()
                    count += 1
                elif p.is_dir():
                    shutil.rmtree(p)
                    count += 1
            except Exception:
                logger.warning("Could not delete %s", p)
    logger.info("Cleaned up %d item(s) from output/", count)
    return count


async def cleanup_expired() -> None:
    """Background task: remove sessions idle longer than TTL."""
    while True:
        await asyncio.sleep(300)  # check every 5 minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES)
        async with _lock:
            expired = [
                sid for sid, s in _sessions.items()
                if s.last_active < cutoff
            ]
            for sid in expired:
                # Save to disk before removing from memory
                s = _sessions[sid]
                if s.history:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, _save_session_sync, s)
                del _sessions[sid]
            if expired:
                logger.info("Cleaned up %d expired session(s) (saved to disk)", len(expired))