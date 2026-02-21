"""
pattern_engine.py — Usage pattern detection for Friday (Phase 3).

Tracks frequency of actions, commands, apps, and time-of-day clusters
to detect repeating behaviour and suggest proactive actions.
"""

import logging
import time
from datetime import datetime

from app import database as db

logger = logging.getLogger(__name__)


# ── Record observations ──────────────────────────────────────────────────────

async def record_action(pattern_type: str, key: str) -> None:
    """
    Increment the counter for a pattern_type+key pair.
    Uses UPSERT to create or update.

    pattern_type examples: 'command', 'app', 'mode_switch', 'build', 'time_cluster'
    key examples:          'ls', 'code', 'coding', 'docker build', '09:00-10:00'
    """
    now = time.time()
    await db.execute(
        """
        INSERT INTO patterns (pattern_type, key, count, last_seen)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(pattern_type, key)
        DO UPDATE SET count = count + 1, last_seen = ?
        """,
        (pattern_type, key, now, now),
    )


async def record_time_cluster() -> None:
    """Record the current hour as a time-cluster observation."""
    hour = datetime.now().strftime("%H:00-%H:59")
    await record_action("time_cluster", hour)


# ── Analysis ─────────────────────────────────────────────────────────────────

async def analyze_patterns() -> list[dict]:
    """
    Return all patterns sorted by frequency (highest first).
    Only returns patterns with count >= 3 to filter noise.
    """
    rows = await db.query(
        "SELECT pattern_type, key, count, last_seen FROM patterns "
        "WHERE count >= 3 ORDER BY count DESC LIMIT 50"
    )
    return rows


async def get_top_commands(n: int = 10) -> list[dict]:
    """Return the most frequently used commands."""
    return await db.query(
        "SELECT key, count FROM patterns WHERE pattern_type = 'command' "
        "ORDER BY count DESC LIMIT ?",
        (n,),
    )


async def get_top_apps(n: int = 10) -> list[dict]:
    """Return the most frequently opened apps."""
    return await db.query(
        "SELECT key, count FROM patterns WHERE pattern_type = 'app' "
        "ORDER BY count DESC LIMIT ?",
        (n,),
    )


async def get_time_clusters() -> list[dict]:
    """Return activity time clusters."""
    return await db.query(
        "SELECT key as hour_range, count FROM patterns "
        "WHERE pattern_type = 'time_cluster' ORDER BY count DESC"
    )


# ── Suggestions from patterns ────────────────────────────────────────────────

async def get_suggestions_from_patterns() -> list[str]:
    """
    Generate proactive suggestion strings based on detected patterns.
    Returns a list of human-readable suggestions.
    """
    suggestions: list[str] = []

    # Top commands
    top_cmds = await get_top_commands(3)
    for cmd in top_cmds:
        if cmd["count"] >= 5:
            suggestions.append(
                f"You frequently run '{cmd['key']}' ({cmd['count']} times). "
                f"Want me to automate this?"
            )

    # Top apps
    top_apps = await get_top_apps(3)
    for app in top_apps:
        if app["count"] >= 5:
            suggestions.append(
                f"You often open '{app['key']}' ({app['count']} times). "
                f"Shall I launch it?"
            )

    # Time clusters
    clusters = await get_time_clusters()
    current_hour = datetime.now().strftime("%H:00-%H:59")
    for cluster in clusters:
        if cluster["hour_range"] == current_hour and cluster["count"] >= 3:
            suggestions.append(
                f"You're usually active around {current_hour}. "
                f"I've noticed this {cluster['count']} times."
            )

    return suggestions
