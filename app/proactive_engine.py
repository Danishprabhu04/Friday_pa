"""
proactive_engine.py — Proactive suggestion engine for Friday (Phase 3).

Analyses system state, patterns, and recent events to generate
helpful suggestions.  Never auto-executes — only suggests.
"""

import logging
import time

from app import database as db
from app.config_loader import Settings
from app.pattern_engine import get_suggestions_from_patterns
from app.state_manager import SystemState

logger = logging.getLogger(__name__)

# ── In-memory suggestion cache ───────────────────────────────────────────────
_suggestions: list[dict] = []


async def generate_suggestions(state: SystemState, settings: Settings) -> list[dict]:
    """
    Analyse current conditions and produce a list of suggestion dicts.

    Each suggestion: {"type": ..., "message": ..., "priority": "low"|"medium"|"high"}
    """
    global _suggestions
    suggestions: list[dict] = []

    # ── System stress suggestions ────────────────────────────────────────
    if state.is_system_stressed(settings):
        if state.cpu_percent > settings.cpu_threshold:
            suggestions.append({
                "type": "resource",
                "message": f"CPU is at {state.cpu_percent:.0f}%. Consider closing heavy processes.",
                "priority": "high",
            })
        if state.ram_available_mb < 500:
            suggestions.append({
                "type": "resource",
                "message": f"RAM available is only {state.ram_available_mb:.0f} MB. Consider freeing memory.",
                "priority": "high",
            })
        if state.gpu_utilization and state.gpu_utilization > settings.gpu_threshold:
            suggestions.append({
                "type": "resource",
                "message": f"GPU at {state.gpu_utilization}%. Heavy GPU tasks may slow the system.",
                "priority": "high",
            })

    # ── Mode suggestions ─────────────────────────────────────────────────
    idle_seconds = time.time() - state.last_activity
    if idle_seconds > 1800 and state.mode != "idle":  # 30 min
        suggestions.append({
            "type": "mode",
            "message": "You've been inactive for 30+ minutes. Switching to idle mode would save resources.",
            "priority": "low",
        })

    # ── Pattern-based suggestions ────────────────────────────────────────
    try:
        pattern_suggestions = await get_suggestions_from_patterns()
        for msg in pattern_suggestions:
            suggestions.append({
                "type": "pattern",
                "message": msg,
                "priority": "medium",
            })
    except Exception as exc:
        logger.error("Pattern suggestion error: %s", exc)

    # ── Recent failure suggestions ───────────────────────────────────────
    try:
        failure_rows = await db.query(
            "SELECT COUNT(*) as c FROM resource_events "
            "WHERE event_type = 'failure' AND timestamp >= ?",
            (time.time() - 3600,),
        )
        failure_count = failure_rows[0]["c"] if failure_rows else 0
        if failure_count >= 3:
            suggestions.append({
                "type": "reflection",
                "message": f"{failure_count} command failures in the last hour. Consider running simpler tasks.",
                "priority": "medium",
            })
    except Exception as exc:
        logger.error("Failure suggestion error: %s", exc)

    _suggestions = suggestions
    if suggestions:
        logger.info("Generated %d proactive suggestions", len(suggestions))
    return suggestions


def get_cached_suggestions() -> list[dict]:
    """Return the most recently generated suggestions."""
    return _suggestions
