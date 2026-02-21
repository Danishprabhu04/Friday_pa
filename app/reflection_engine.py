"""
reflection_engine.py — Self-improvement logic for Friday (Phase 3).

Tracks failures, rejections, and overrides.  When too many failures
accumulate within a time window, Friday enters safe mode to protect
the system.
"""

import logging
import time

from app import database as db

logger = logging.getLogger(__name__)

# ── Safe mode state ──────────────────────────────────────────────────────────
_safe_mode: bool = False


def is_safe_mode() -> bool:
    return _safe_mode


def set_safe_mode(enabled: bool) -> dict:
    """Force-enable or disable safe mode."""
    global _safe_mode
    old = _safe_mode
    _safe_mode = enabled
    if enabled:
        logger.warning("Safe mode ENABLED (manual override)")
    else:
        logger.info("Safe mode DISABLED (manual override)")
    return {"status": "ok", "safe_mode": _safe_mode, "previous": old}


# ── Record outcomes ──────────────────────────────────────────────────────────

async def record_outcome(event_type: str, details: str = "") -> None:
    """
    Record a task outcome for reflection analysis.

    event_type: 'failure', 'blocked', 'permission_denied', 'timeout', 'override', 'success'
    """
    await db.insert(
        "resource_events",
        event_type=event_type,
        details=details,
        timestamp=time.time(),
    )
    logger.debug("Reflection recorded: %s — %s", event_type, details)


# ── Analysis ─────────────────────────────────────────────────────────────────

async def get_failure_count(window_minutes: int = 60) -> int:
    """Count failures within the last N minutes."""
    cutoff = time.time() - (window_minutes * 60)
    rows = await db.query(
        "SELECT COUNT(*) as c FROM resource_events "
        "WHERE event_type IN ('failure', 'blocked', 'timeout') "
        "AND timestamp >= ?",
        (cutoff,),
    )
    return rows[0]["c"] if rows else 0


async def get_recent_failures(n: int = 10) -> list[dict]:
    """Return the last N failure events."""
    return await db.query(
        "SELECT event_type, details, timestamp FROM resource_events "
        "WHERE event_type IN ('failure', 'blocked', 'timeout', 'permission_denied') "
        "ORDER BY id DESC LIMIT ?",
        (n,),
    )


async def should_enter_safe_mode(threshold: int) -> bool:
    """
    Check if failure count exceeds threshold.
    If so, automatically activate safe mode.
    """
    global _safe_mode

    count = await get_failure_count(window_minutes=60)

    if count >= threshold and not _safe_mode:
        _safe_mode = True
        logger.warning(
            "Safe mode AUTO-ACTIVATED: %d failures in last 60 min (threshold: %d)",
            count, threshold,
        )
        await db.insert(
            "optimization_log",
            action="safe_mode_activated",
            reason=f"{count} failures in 60 min",
            timestamp=time.time(),
        )
        return True

    return False


async def get_reflection_status() -> dict:
    """Return the current reflection state for the API."""
    failure_count = await get_failure_count()
    recent = await get_recent_failures(5)
    return {
        "safe_mode": _safe_mode,
        "failures_last_60min": failure_count,
        "recent_failures": recent,
    }
