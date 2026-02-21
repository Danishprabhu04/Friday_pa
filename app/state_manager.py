"""
state_manager.py — Centralised system state for Friday (Phase 3).

Tracks mode, resource metrics, loaded models, active tasks, stress flag,
monitoring frequency, safe mode, and last-activity timestamp.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config_loader import Settings
from app.monitor import get_system_status

logger = logging.getLogger(__name__)

# ── Valid operating modes ────────────────────────────────────────────────────
VALID_MODES = {"idle", "monitor", "coding", "voice", "heavy"}
HEAVY_MODES = {"voice", "heavy"}


@dataclass
class SystemState:
    """In-memory singleton that every module can inspect."""

    # Current operating mode
    mode: str = "idle"

    # Latest resource readings (populated by refresh())
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_available_mb: float = 0.0
    gpu_utilization: int | None = None
    gpu_memory_used_mb: int | None = None

    # Stress tracking
    _cpu_high_since: float | None = field(default=None, repr=False)

    # Model & task tracking
    loaded_models: list[str] = field(default_factory=list)
    active_tasks: list[str] = field(default_factory=list)

    # Timestamps
    last_activity: float = field(default_factory=time.time)

    # Phase 3 additions
    monitoring_frequency: str = "normal"   # normal | reduced
    _previous_mode: str = field(default="idle", repr=False)  # for wake restore

    # ── Refresh from live metrics ────────────────────────────────────────

    async def refresh(self) -> None:
        """Pull latest CPU / RAM / GPU readings from monitor.py."""
        status = await get_system_status()

        self.cpu_percent = status["cpu_percent"]
        self.ram_percent = status["ram"]["percent"]
        # Available RAM in MB
        total_gb = status["ram"]["total_gb"]
        used_gb = status["ram"]["used_gb"]
        self.ram_available_mb = round((total_gb - used_gb) * 1024, 1)

        gpu = status.get("gpu")
        if gpu:
            self.gpu_utilization = gpu.get("utilization_percent")
            self.gpu_memory_used_mb = gpu.get("memory_used_mb")
        else:
            self.gpu_utilization = None
            self.gpu_memory_used_mb = None

    # ── Mode switching ───────────────────────────────────────────────────

    def switch_mode(self, new_mode: str) -> dict:
        """
        Switch operating mode.  Enforces one-heavy-at-a-time rule.
        Saves previous mode for wake restore.
        Returns a status dict.
        """
        if new_mode not in VALID_MODES:
            return {"status": "error", "reason": f"Invalid mode: {new_mode}. Valid: {VALID_MODES}"}

        old = self.mode

        # If entering a heavy mode, unload any current heavy mode first
        if new_mode in HEAVY_MODES and self.mode in HEAVY_MODES and self.mode != new_mode:
            logger.info("Unloading heavy mode '%s' before switching to '%s'", self.mode, new_mode)

        # Save for wake restore
        if new_mode == "idle" and old != "idle":
            self._previous_mode = old

        self.mode = new_mode
        self.touch()

        # Adjust monitoring frequency
        if new_mode == "idle":
            self.monitoring_frequency = "reduced"
        elif self.monitoring_frequency == "reduced":
            self.monitoring_frequency = "normal"

        logger.info("Mode switched: %s → %s", old, new_mode)
        return {"status": "ok", "previous_mode": old, "current_mode": new_mode}

    def wake(self) -> dict:
        """Restore the last working mode when activity resumes after idle."""
        if self.mode == "idle" and self._previous_mode != "idle":
            logger.info("Waking from idle → restoring mode '%s'", self._previous_mode)
            return self.switch_mode(self._previous_mode)
        return {"status": "already_active", "mode": self.mode}

    # ── Idle detection ───────────────────────────────────────────────────

    def check_idle(self, idle_timeout_minutes: int) -> bool:
        """
        If last activity exceeds idle_timeout_minutes, switch to idle.
        Returns True if auto-switched.
        """
        if self.mode == "idle":
            return False

        elapsed = time.time() - self.last_activity
        if elapsed >= idle_timeout_minutes * 60:
            logger.info(
                "Idle timeout reached (%.0fs). Auto-switching to idle.", elapsed
            )
            self.switch_mode("idle")
            return True
        return False

    # ── Stress detection ─────────────────────────────────────────────────

    def is_system_stressed(self, settings: Settings) -> bool:
        """
        Return True if any stress condition is met:
          • CPU > threshold for longer than stress_cpu_duration_seconds
          • RAM available < 500 MB
          • GPU utilisation > gpu_threshold
        """
        now = time.time()

        # CPU sustained high
        cpu_stressed = False
        if self.cpu_percent > settings.cpu_threshold:
            if self._cpu_high_since is None:
                self._cpu_high_since = now
            elif now - self._cpu_high_since >= settings.stress_cpu_duration_seconds:
                cpu_stressed = True
        else:
            self._cpu_high_since = None

        ram_stressed = self.ram_available_mb < 500

        gpu_stressed = (
            self.gpu_utilization is not None
            and self.gpu_utilization > settings.gpu_threshold
        )

        stressed = cpu_stressed or ram_stressed or gpu_stressed
        if stressed:
            reasons = []
            if cpu_stressed:
                reasons.append(f"CPU {self.cpu_percent:.0f}% (>{settings.cpu_threshold}% sustained)")
            if ram_stressed:
                reasons.append(f"RAM available {self.ram_available_mb:.0f} MB (<500 MB)")
            if gpu_stressed:
                reasons.append(f"GPU {self.gpu_utilization}% (>{settings.gpu_threshold}%)")
            logger.warning("System stress detected: %s", "; ".join(reasons))

        return stressed

    # ── Snapshot for API ─────────────────────────────────────────────────

    def snapshot(self, settings: Settings) -> dict:
        """Return a JSON-serialisable representation of the full system state."""
        return {
            "mode": self.mode,
            "cpu_percent": self.cpu_percent,
            "ram_percent": self.ram_percent,
            "ram_available_mb": self.ram_available_mb,
            "gpu_utilization": self.gpu_utilization,
            "gpu_memory_used_mb": self.gpu_memory_used_mb,
            "is_stressed": self.is_system_stressed(settings),
            "monitoring_frequency": self.monitoring_frequency,
            "loaded_models": self.loaded_models,
            "active_tasks": self.active_tasks,
            "last_activity_seconds_ago": round(time.time() - self.last_activity, 1),
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    def touch(self) -> None:
        """Record current time as last activity."""
        self.last_activity = time.time()
