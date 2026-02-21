"""
decision_engine.py — Resource-aware decision gate for Friday (Phase 3).

Before any command executes, this module evaluates:
  1. Task cost estimate  (low / medium / high)
  2. Current system stress
  3. Command risk level
  4. Safe-mode restrictions (Phase 3)

…and returns one of: execute, delay, ask_permission, reject, switch_mode.
"""

import logging
import re
from dataclasses import dataclass

from app.config_loader import Settings
from app.reflection_engine import is_safe_mode

logger = logging.getLogger(__name__)

# ── Task cost keywords ───────────────────────────────────────────────────────
# Maps regex patterns to cost levels.  First match wins.

_COST_RULES: list[tuple[str, str]] = [
    # High cost
    (r"\btrain\b", "high"),
    (r"\bcompil(e|ing)\b", "high"),
    (r"\bbuild\b.*\bdocker\b", "high"),
    (r"\bdocker\s+build\b", "high"),
    (r"\bmake\b.*\ball\b", "high"),
    (r"\bheavy\b", "high"),
    (r"\bmodel\b.*\b(run|load|train)\b", "high"),
    (r"\bffmpeg\b", "high"),
    (r"\bblender\b", "high"),
    (r"\bcuda\b", "high"),
    # Medium cost
    (r"\bpip\s+install\b", "medium"),
    (r"\bnpm\s+install\b", "medium"),
    (r"\bgit\s+(clone|pull)\b", "medium"),
    (r"\bwget\b", "medium"),
    (r"\bcurl\b.*\b-[oO]\b", "medium"),
    (r"\bdocker\b", "medium"),
    (r"\btar\b", "medium"),
    (r"\bzip\b", "medium"),
    (r"\bunzip\b", "medium"),
    (r"\bcp\s+-r\b", "medium"),
]

_COST_PATTERNS = [(re.compile(pat, re.IGNORECASE), cost) for pat, cost in _COST_RULES]

# Cost ordering for safe-mode comparison
_COST_LEVELS = {"low": 0, "medium": 1, "high": 2}


def estimate_cost(instruction: str, command: str) -> str:
    """Estimate the resource cost of a task as 'low', 'medium', or 'high'."""
    combined = f"{instruction} {command}"
    for pattern, cost in _COST_PATTERNS:
        if pattern.search(combined):
            return cost
    return "low"


# ── Decision result ──────────────────────────────────────────────────────────

@dataclass
class Decision:
    """Structured output from the decision engine."""

    action: str                  # execute | delay | ask_permission | reject | switch_mode
    reason: str                  # human-readable explanation
    estimated_cost: str          # low | medium | high
    suggested_mode: str | None = None  # suggested mode to switch to (if action == switch_mode)


def decide(
    instruction: str,
    command: str,
    risk_level: str,
    is_stressed: bool,
    settings: Settings,
) -> Decision:
    """
    Evaluate whether a task should proceed, be delayed, or be blocked.

    Phase 3 addition: safe-mode check.  When safe mode is active,
    only tasks at or below `safe_mode_max_cost` are allowed.

    Logic matrix:
      ┌──────────┬────────────┬───────────┬──────────────────────────┐
      │ Cost     │ Stressed?  │ Risk      │ Action                   │
      ├──────────┼────────────┼───────────┼──────────────────────────┤
      │ any      │ —          │ dangerous │ reject                   │
      │ > max    │ safe mode  │ —         │ reject (safe mode)       │
      │ any      │ yes        │ moderate  │ ask_permission           │
      │ high     │ yes        │ safe      │ delay / switch_mode      │
      │ high     │ no         │ safe      │ execute                  │
      │ low/med  │ no         │ safe/mod  │ execute                  │
      │ low/med  │ yes        │ safe      │ execute (with warning)   │
      └──────────┴────────────┴───────────┴──────────────────────────┘
    """

    cost = estimate_cost(instruction, command)

    # — Always reject dangerous ------------------------------------------------
    if risk_level == "dangerous":
        d = Decision(
            action="reject",
            reason="Command classified as dangerous — always blocked.",
            estimated_cost=cost,
        )
        logger.warning("Decision: REJECT (dangerous) — %s", command)
        return d

    # — Safe mode: reject if cost > allowed max ────────────────────────────────
    if is_safe_mode():
        max_allowed = _COST_LEVELS.get(settings.safe_mode_max_cost, 0)
        task_cost = _COST_LEVELS.get(cost, 0)
        if task_cost > max_allowed:
            d = Decision(
                action="reject",
                reason=(
                    f"Safe mode is active. Only '{settings.safe_mode_max_cost}' cost "
                    f"tasks allowed, but this task is '{cost}'."
                ),
                estimated_cost=cost,
            )
            logger.warning("Decision: REJECT (safe mode, cost=%s) — %s", cost, command)
            return d

    # — Stressed + moderate → ask -----------------------------------------------
    if is_stressed and risk_level == "moderate":
        d = Decision(
            action="ask_permission",
            reason="System is under stress and command is moderate-risk. Permission required.",
            estimated_cost=cost,
        )
        logger.info("Decision: ASK_PERMISSION (stressed + moderate) — %s", command)
        return d

    # — High cost + stressed → delay / switch mode ------------------------------
    if cost == "high" and is_stressed:
        d = Decision(
            action="switch_mode",
            reason=(
                "System is under stress and this is a high-cost task. "
                "Recommend switching to idle or unloading current tasks before proceeding."
            ),
            estimated_cost=cost,
            suggested_mode="idle",
        )
        logger.info("Decision: SWITCH_MODE (high cost + stressed) — %s", command)
        return d

    # — Moderate risk (not stressed) + config says ask --------------------------
    if risk_level == "moderate" and settings.ask_permission_for_moderate:
        d = Decision(
            action="ask_permission",
            reason="Command is moderate-risk. Permission required per configuration.",
            estimated_cost=cost,
        )
        logger.info("Decision: ASK_PERMISSION (moderate, config) — %s", command)
        return d

    # — Low/medium cost + stressed → execute with warning ----------------------
    if is_stressed:
        d = Decision(
            action="execute",
            reason=(
                "System is under stress, but this is a low-impact task. "
                "Proceeding with caution."
            ),
            estimated_cost=cost,
        )
        logger.info("Decision: EXECUTE (stressed, low cost) — %s", command)
        return d

    # — Default: safe to execute -----------------------------------------------
    d = Decision(
        action="execute",
        reason="Task is safe and system resources are adequate.",
        estimated_cost=cost,
    )
    logger.info("Decision: EXECUTE — %s", command)
    return d
