"""
config_loader.py — Loads config.yaml and .env for Friday (Phase 3).
"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── Locate project root (one level above app/) ──────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from project root
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class Settings:
    """Runtime configuration for Friday."""

    # Language preference
    language: str = "both"

    # System-monitoring thresholds (%)
    cpu_threshold: int = 85
    ram_threshold: int = 80
    gpu_threshold: int = 90

    # Permission control
    ask_permission_for_moderate: bool = True

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"

    # Command execution
    command_timeout: int = 10

    # Self-limiting behaviour (Phase 2)
    idle_timeout_minutes: int = 5
    stress_cpu_duration_seconds: int = 300
    auto_unload: bool = True
    model_unload_timeout_minutes: int = 10

    # Autonomous intelligence (Phase 3)
    personality: str = "professional"
    memory_max_rows: int = 500
    pattern_analysis_interval: int = 300
    proactive_interval: int = 600
    reflection_failure_threshold: int = 5
    safe_mode_max_cost: str = "low"
    background_loop_interval: int = 30
    db_path: str = "data/friday.db"


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
        gpu_threshold=int(data.get("gpu_threshold", Settings.gpu_threshold)),
        ask_permission_for_moderate=bool(
            data.get("ask_permission_for_moderate", Settings.ask_permission_for_moderate)
        ),
        openrouter_api_key=api_key,
        openrouter_model=data.get("openrouter_model", Settings.openrouter_model),
        command_timeout=int(data.get("command_timeout", Settings.command_timeout)),
        idle_timeout_minutes=int(data.get("idle_timeout_minutes", Settings.idle_timeout_minutes)),
        stress_cpu_duration_seconds=int(
            data.get("stress_cpu_duration_seconds", Settings.stress_cpu_duration_seconds)
        ),
        auto_unload=bool(data.get("auto_unload", Settings.auto_unload)),
        model_unload_timeout_minutes=int(
            data.get("model_unload_timeout_minutes", Settings.model_unload_timeout_minutes)
        ),
        personality=data.get("personality", Settings.personality),
        memory_max_rows=int(data.get("memory_max_rows", Settings.memory_max_rows)),
        pattern_analysis_interval=int(
            data.get("pattern_analysis_interval", Settings.pattern_analysis_interval)
        ),
        proactive_interval=int(data.get("proactive_interval", Settings.proactive_interval)),
        reflection_failure_threshold=int(
            data.get("reflection_failure_threshold", Settings.reflection_failure_threshold)
        ),
        safe_mode_max_cost=data.get("safe_mode_max_cost", Settings.safe_mode_max_cost),
        background_loop_interval=int(
            data.get("background_loop_interval", Settings.background_loop_interval)
        ),
        db_path=data.get("db_path", Settings.db_path),
    )
