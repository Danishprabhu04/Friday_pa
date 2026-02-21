"""
model_controller.py — Logical model lifecycle manager (Phase 2).

Currently OpenRouter is cloud-only, so these are bookkeeping operations
that update SystemState.  This module is structured so swapping in local
model loading (e.g. Ollama, llama.cpp) later is straightforward.
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ModelRecord:
    """Metadata for a logically loaded model."""
    name: str
    loaded_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


class ModelController:
    """Track which logical models are 'active' and auto-unload stale ones."""

    def __init__(self) -> None:
        self._models: dict[str, ModelRecord] = {}

    # ── Load / unload ────────────────────────────────────────────────────

    def load_model(self, name: str) -> dict:
        """Mark a model as loaded."""
        if name in self._models:
            self._models[name].last_used = time.time()
            logger.info("Model '%s' already loaded — refreshed timestamp", name)
            return {"status": "already_loaded", "model": name}

        self._models[name] = ModelRecord(name=name)
        logger.info("Model '%s' loaded", name)
        return {"status": "loaded", "model": name}

    def unload_model(self, name: str) -> dict:
        """Mark a model as unloaded."""
        if name not in self._models:
            return {"status": "not_loaded", "model": name}

        del self._models[name]
        logger.info("Model '%s' unloaded", name)
        return {"status": "unloaded", "model": name}

    def touch_model(self, name: str) -> None:
        """Update last_used timestamp for a model (called on each LLM request)."""
        if name in self._models:
            self._models[name].last_used = time.time()

    # ── Auto-unload ──────────────────────────────────────────────────────

    def auto_unload_check(self, timeout_minutes: int) -> list[str]:
        """
        Unload models that haven't been used for longer than timeout_minutes.
        Returns list of model names that were unloaded.
        """
        now = time.time()
        cutoff = timeout_minutes * 60
        stale = [
            name for name, rec in self._models.items()
            if (now - rec.last_used) >= cutoff
        ]
        for name in stale:
            self.unload_model(name)
            logger.info("Auto-unloaded stale model '%s' (idle > %d min)", name, timeout_minutes)
        return stale

    # ── Query ────────────────────────────────────────────────────────────

    def get_active_models(self) -> list[dict]:
        """Return a list of currently loaded models with metadata."""
        now = time.time()
        return [
            {
                "name": rec.name,
                "loaded_seconds_ago": round(now - rec.loaded_at, 1),
                "last_used_seconds_ago": round(now - rec.last_used, 1),
            }
            for rec in self._models.values()
        ]

    def is_loaded(self, name: str) -> bool:
        return name in self._models
