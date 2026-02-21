"""
memory_manager.py — Persistent memory for Friday (Phase 3).

Stores conversations, tasks, and events in SQLite via database.py.
Provides retrieval, summarisation, and cleanup.
"""

import logging
import time

from app import database as db

logger = logging.getLogger(__name__)


# ── Store operations ─────────────────────────────────────────────────────────

async def store_conversation(role: str, content: str) -> int:
    """Save a conversation message (user or assistant)."""
    row_id = await db.insert("conversations", role=role, content=content, timestamp=time.time())
    logger.debug("Stored conversation [%s] id=%d", role, row_id)
    return row_id


async def store_task(instruction: str, command: str | None, status: str, cost: str | None) -> int:
    """Save an executed (or blocked) task."""
    row_id = await db.insert(
        "tasks",
        instruction=instruction,
        command=command or "",
        status=status,
        cost=cost or "",
        timestamp=time.time(),
    )
    logger.debug("Stored task id=%d status=%s", row_id, status)
    return row_id


async def store_event(event_type: str, details: str = "") -> int:
    """Save a resource/system event (stress, mode switch, etc.)."""
    row_id = await db.insert(
        "resource_events",
        event_type=event_type,
        details=details,
        timestamp=time.time(),
    )
    logger.debug("Stored event id=%d type=%s", row_id, event_type)
    return row_id


# ── Retrieve operations ─────────────────────────────────────────────────────

async def get_recent_conversations(n: int = 10) -> list[dict]:
    """Return the last N conversation messages."""
    return await db.query(
        "SELECT role, content, timestamp FROM conversations ORDER BY id DESC LIMIT ?",
        (n,),
    )


async def get_recent_tasks(n: int = 20) -> list[dict]:
    """Return the last N tasks."""
    return await db.query(
        "SELECT instruction, command, status, cost, timestamp FROM tasks ORDER BY id DESC LIMIT ?",
        (n,),
    )


async def get_recent_events(n: int = 20) -> list[dict]:
    """Return the last N resource events."""
    return await db.query(
        "SELECT event_type, details, timestamp FROM resource_events ORDER BY id DESC LIMIT ?",
        (n,),
    )


async def get_memory_summary() -> dict:
    """Return counts and basic stats for all memory tables."""
    return {
        "conversations": await db.count("conversations"),
        "tasks": await db.count("tasks"),
        "resource_events": await db.count("resource_events"),
        "patterns": await db.count("patterns"),
    }


# ── Memory for LLM context injection ────────────────────────────────────────

async def get_context_messages(n: int = 6) -> list[dict]:
    """
    Return the last N messages formatted for LLM context injection.
    Returns in chronological order (oldest first).
    """
    rows = await db.query(
        "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
        (n,),
    )
    # Reverse so oldest is first (chronological)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


# ── Cleanup ──────────────────────────────────────────────────────────────────

async def clear_memory() -> dict:
    """Wipe conversations and tasks (keeps patterns and preferences)."""
    await db.execute("DELETE FROM conversations")
    await db.execute("DELETE FROM tasks")
    await db.execute("DELETE FROM resource_events")
    logger.info("Memory cleared (conversations, tasks, events)")
    return {"status": "cleared"}


async def auto_summarise(max_rows: int) -> bool:
    """
    If conversations exceed max_rows, keep the most recent half
    and insert a summary marker.  Returns True if summarisation happened.
    """
    current = await db.count("conversations")
    if current <= max_rows:
        return False

    keep = max_rows // 2
    # Delete oldest rows, keeping the last `keep`
    await db.execute(
        "DELETE FROM conversations WHERE id NOT IN "
        "(SELECT id FROM conversations ORDER BY id DESC LIMIT ?)",
        (keep,),
    )
    # Insert summary marker
    await db.insert(
        "conversations",
        role="system",
        content=f"[Memory auto-summarised: {current - keep} older messages removed]",
        timestamp=time.time(),
    )
    logger.info("Auto-summarised memory: kept %d of %d conversations", keep, current)
    return True
