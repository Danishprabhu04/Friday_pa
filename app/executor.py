"""
executor.py — Safe command execution pipeline (Phase 3).

Full 4-layer safety chain:
  1. Permission filter  → classify risk
  2. Decision engine    → cost + stress + safe-mode check
  3. Reflection engine  → record outcome (success/failure)
  4. Memory manager     → store task in DB
"""

import asyncio
import logging

from app.brain import generate_command
from app.config_loader import Settings
from app.decision_engine import decide, Decision
from app.memory_manager import store_task
from app.pattern_engine import record_action
from app.permission import classify_command
from app.reflection_engine import record_outcome
from app.state_manager import SystemState

logger = logging.getLogger(__name__)


async def execute_instruction(
    instruction: str,
    settings: Settings,
    state: SystemState,
) -> dict:
    """
    End-to-end pipeline:
      instruction → command → risk → decision → execution → reflection → memory.

    Returns a dict with: status, command, risk_level, decision, output, error.
    """

    # ── Layer 0: Generate command from LLM ───────────────────────────────
    command = await generate_command(instruction, settings)

    if command.startswith("Error:"):
        await store_task(instruction, None, "error", None)
        await record_outcome("failure", f"LLM error: {command}")
        return {
            "status": "error",
            "command": None,
            "risk_level": None,
            "decision": None,
            "output": None,
            "error": command,
        }

    # ── Layer 1: Permission filter ───────────────────────────────────────
    risk_level = classify_command(command)

    # ── Layer 2: Decision engine ─────────────────────────────────────────
    await state.refresh()
    is_stressed = state.is_system_stressed(settings)

    decision: Decision = decide(
        instruction=instruction,
        command=command,
        risk_level=risk_level,
        is_stressed=is_stressed,
        settings=settings,
    )

    decision_dict = {
        "action": decision.action,
        "reason": decision.reason,
        "estimated_cost": decision.estimated_cost,
        "suggested_mode": decision.suggested_mode,
    }

    # Handle non-execute decisions
    if decision.action == "reject":
        logger.warning("BLOCKED dangerous command: %s", command)
        await store_task(instruction, command, "blocked", decision.estimated_cost)
        await record_outcome("blocked", command)
        return {
            "status": "blocked",
            "command": command,
            "risk_level": risk_level,
            "decision": decision_dict,
            "output": None,
            "error": decision.reason,
        }

    if decision.action == "ask_permission":
        logger.info("Permission required: %s", command)
        await store_task(instruction, command, "permission_required", decision.estimated_cost)
        await record_outcome("permission_denied", command)
        return {
            "status": "permission_required",
            "command": command,
            "risk_level": risk_level,
            "decision": decision_dict,
            "output": None,
            "error": None,
        }

    if decision.action in ("delay", "switch_mode"):
        logger.info("Decision: %s — %s", decision.action, decision.reason)
        await store_task(instruction, command, decision.action, decision.estimated_cost)
        return {
            "status": decision.action,
            "command": command,
            "risk_level": risk_level,
            "decision": decision_dict,
            "output": None,
            "error": None,
        }

    # ── Execute safe command ─────────────────────────────────────────────
    state.touch()
    result = await _run_command(command, timeout=settings.command_timeout, decision=decision_dict)

    # ── Layer 3: Reflection — record outcome ─────────────────────────────
    if result["status"] == "success":
        await record_outcome("success", command)
    else:
        await record_outcome("failure", f"{result['status']}: {command}")

    # ── Layer 4: Memory — store task ─────────────────────────────────────
    await store_task(instruction, command, result["status"], decision.estimated_cost)

    # Record pattern for command usage
    await record_action("command", command.split()[0] if command else "unknown")

    return result


async def _run_command(command: str, timeout: int = 10, decision: dict | None = None) -> dict:
    """Run a shell command via subprocess with a timeout."""

    logger.info("Executing command: %s", command)

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        stdout_text = stdout.decode().strip()
        stderr_text = stderr.decode().strip()

        if proc.returncode == 0:
            logger.info("Command succeeded (exit 0)")
            return {
                "status": "success",
                "command": command,
                "risk_level": "safe",
                "decision": decision,
                "output": stdout_text,
                "error": None,
            }
        else:
            logger.warning("Command failed (exit %d): %s", proc.returncode, stderr_text)
            return {
                "status": "failed",
                "command": command,
                "risk_level": "safe",
                "decision": decision,
                "output": stdout_text,
                "error": stderr_text,
            }

    except asyncio.TimeoutError:
        logger.error("Command timed out after %ds: %s", timeout, command)
        return {
            "status": "timeout",
            "command": command,
            "risk_level": "safe",
            "decision": decision,
            "output": None,
            "error": f"Command timed out after {timeout} seconds.",
        }
    except Exception as exc:
        logger.error("Execution error: %s", exc)
        return {
            "status": "error",
            "command": command,
            "risk_level": "safe",
            "decision": decision,
            "output": None,
            "error": str(exc),
        }
