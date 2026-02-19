"""
executor.py — Safe command execution pipeline.

Flow:
  1. User sends natural-language instruction.
  2. brain.generate_command() turns it into a shell command.
  3. permission.classify_command() assesses risk.
  4. If safe → run.  If moderate → check config.  If dangerous → block.
  5. Output + logs returned to caller.
"""

import asyncio
import logging

from app.brain import generate_command
from app.config_loader import Settings
from app.permission import classify_command

logger = logging.getLogger(__name__)


async def execute_instruction(instruction: str, settings: Settings) -> dict:
    """
    End-to-end: instruction → command → risk check → (optional) execution.

    Returns a dict with keys: status, command, risk_level, output, error.
    """

    # Step 1 — Ask the LLM to produce a shell command
    command = await generate_command(instruction, settings)

    if command.startswith("Error:"):
        return {
            "status": "error",
            "command": None,
            "risk_level": None,
            "output": None,
            "error": command,
        }

    # Step 2 — Classify risk
    risk_level = classify_command(command)

    # Step 3 — Act on risk level
    if risk_level == "dangerous":
        logger.warning("BLOCKED dangerous command: %s", command)
        return {
            "status": "blocked",
            "command": command,
            "risk_level": risk_level,
            "output": None,
            "error": "This command has been classified as dangerous and was blocked.",
        }

    if risk_level == "moderate" and settings.ask_permission_for_moderate:
        logger.info("Permission required for moderate command: %s", command)
        return {
            "status": "permission_required",
            "command": command,
            "risk_level": risk_level,
            "output": None,
            "error": None,
        }

    # Step 4 — Execute safe (or approved moderate) command
    return await _run_command(command, timeout=settings.command_timeout)


async def _run_command(command: str, timeout: int = 10) -> dict:
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
                "output": stdout_text,
                "error": None,
            }
        else:
            logger.warning("Command failed (exit %d): %s", proc.returncode, stderr_text)
            return {
                "status": "failed",
                "command": command,
                "risk_level": "safe",
                "output": stdout_text,
                "error": stderr_text,
            }

    except asyncio.TimeoutError:
        logger.error("Command timed out after %ds: %s", timeout, command)
        return {
            "status": "timeout",
            "command": command,
            "risk_level": "safe",
            "output": None,
            "error": f"Command timed out after {timeout} seconds.",
        }
    except Exception as exc:
        logger.error("Execution error: %s", exc)
        return {
            "status": "error",
            "command": command,
            "risk_level": "safe",
            "output": None,
            "error": str(exc),
        }
