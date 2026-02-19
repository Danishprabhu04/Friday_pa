"""
logger_setup.py — Structured logging for Friday.

All modules should use:  logger = logging.getLogger(__name__)
"""

import logging
from pathlib import Path

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with console + file handlers (called once at startup)."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(fmt)

    # File handler
    file_handler = logging.FileHandler(log_dir / "friday.log", encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)
