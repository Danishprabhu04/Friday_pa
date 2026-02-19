"""
config_loader.py — Loads config.yaml and .env for Friday.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── Locate project root (one level above app/) ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class Settings:
    """Immutable runtime configuration for Friday."""

    # Language preference
    language: str = "both"

    # System-monitoring thresholds (%)
    cpu_threshold: int = 85
    ram_threshold: int = 80

    # Permission control
    ask_permission_for_moderate: bool = True

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"

    # Command execution
    command_timeout: int = 10


def load_settings() -> Settings:
    """Read config.yaml + environment variables and return a Settings object."""

    config_path = _PROJECT_ROOT / "config.yaml"

    data: dict = {}
    if config_path.exists():
        with open(config_path, "r") as fh:
            data = yaml.safe_load(fh) or {}

    api_key = os.getenv("OPENROUTER_API_KEY", "")

    return Settings(
        language=data.get("language", Settings.language),
        cpu_threshold=int(data.get("cpu_threshold", Settings.cpu_threshold)),
        ram_threshold=int(data.get("ram_threshold", Settings.ram_threshold)),
        ask_permission_for_moderate=bool(
            data.get("ask_permission_for_moderate", Settings.ask_permission_for_moderate)
        ),
        openrouter_api_key=api_key,
        openrouter_model=data.get("openrouter_model", Settings.openrouter_model),
        command_timeout=int(data.get("command_timeout", Settings.command_timeout)),
    )
