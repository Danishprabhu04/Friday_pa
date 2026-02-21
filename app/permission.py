"""
permission.py — Risk classification for shell commands (Phase 2).

Levels:
  • safe       — execute immediately
  • moderate   — ask for confirmation (if configured)
  • dangerous  — always block

Phase 2 addition: stress-aware escalation.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Keyword sets ─────────────────────────────────────────────────────────────

DANGEROUS_KEYWORDS: set[str] = {
    "rm", "sudo", "apt", "systemctl", "chmod", "chown",
    "mkfs", "dd", "kill", "killall", "reboot", "shutdown",
    "fdisk", "parted", "mount", "umount", "iptables",
    "userdel", "useradd", "passwd", "crontab",
}

MODERATE_KEYWORDS: set[str] = {
    "mv", "cp", "pip", "npm", "wget", "curl", "docker",
    "git", "snap", "flatpak", "dpkg",
}

# Pre-compiled patterns for word-boundary matching
_DANGEROUS_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in DANGEROUS_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_MODERATE_RE = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in MODERATE_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def classify_command(command: str) -> str:
    """
    Classify a shell command string as 'safe', 'moderate', or 'dangerous'.

    Uses word-boundary matching to avoid false positives
    (e.g. "format" won't trigger "rm").
    """

    if _DANGEROUS_RE.search(command):
        level = "dangerous"
    elif _MODERATE_RE.search(command):
        level = "moderate"
    else:
        level = "safe"

    logger.info("Command classified as %s: %s", level.upper(), command)
    return level


def classify_with_stress(command: str, is_stressed: bool) -> str:
    """
    Stress-aware classification.

    When the system is under stress, moderate commands are escalated
    to dangerous (blocked).  Safe commands remain safe.
    """
    base_level = classify_command(command)

    if is_stressed and base_level == "moderate":
        logger.warning(
            "Escalating '%s' from MODERATE → DANGEROUS (system stressed)", command
        )
        return "dangerous"

    return base_level
