"""
scheduler.py — Unified autonomous background loop for Friday (Phase 3).

Replaces the Phase 2 idle_check_loop with a single async loop that
handles all periodic tasks with individually-throttled intervals.
"""

import asyncio
import logging
import time

from app import database as db
from app import memory_manager
from app.config_loader import Settings
from app.model_controller import ModelController
from app.proactive_engine import generate_suggestions
from app.pattern_engine import analyze_patterns, record_time_cluster
from app.reflection_engine import should_enter_safe_mode
from app.state_manager import SystemState

logger = logging.getLogger(__name__)


async def autonomous_loop(
    state: SystemState,
    settings: Settings,
    model_ctrl: ModelController,
) -> None:
    """
    Single background loop running every `background_loop_interval` seconds.

    Each tick:
      1. Refresh system state
      2. Check idle timeout
      3. Log stress events
      4. Pattern analysis (throttled)
      5. Proactive suggestions (throttled)
      6. Auto-unload stale models
      7. Auto-summarise memory
      8. Self-optimisation checks
      9. Reflection / safe-mode check
    """

    interval = settings.background_loop_interval
    last_pattern_scan = 0.0
    last_proactive_run = 0.0

    logger.info("Autonomous scheduler started (interval=%ds)", interval)

    while True:
        await asyncio.sleep(interval)
        now = time.time()

        try:
            # ── 1. Refresh system state ──────────────────────────────────
            await state.refresh()

            # ── 2. Idle timeout ──────────────────────────────────────────
            was_idle = state.check_idle(settings.idle_timeout_minutes)
            if was_idle:
                state.monitoring_frequency = "reduced"
                await memory_manager.store_event("idle_switch", "Auto-switched to idle")

            # ── 3. Stress detection ──────────────────────────────────────
            if state.is_system_stressed(settings):
                await memory_manager.store_event(
                    "stress",
                    f"CPU={state.cpu_percent:.0f}% RAM_avail={state.ram_available_mb:.0f}MB "
                    f"GPU={state.gpu_utilization}",
                )

            # ── 4. Pattern analysis (throttled) ──────────────────────────
            if now - last_pattern_scan >= settings.pattern_analysis_interval:
                last_pattern_scan = now
                await record_time_cluster()
                patterns = await analyze_patterns()
                if patterns:
                    logger.info("Pattern scan: %d patterns detected", len(patterns))

            # ── 5. Proactive suggestions (throttled) ─────────────────────
            if now - last_proactive_run >= settings.proactive_interval:
                last_proactive_run = now
                suggestions = await generate_suggestions(state, settings)
                if suggestions:
                    logger.info(
                        "Proactive engine: %d suggestions generated", len(suggestions)
                    )

            # ── 6. Auto-unload stale models ──────────────────────────────
            if settings.auto_unload:
                unloaded = model_ctrl.auto_unload_check(
                    settings.model_unload_timeout_minutes
                )
                if unloaded:
                    state.loaded_models = [
                        m["name"] for m in model_ctrl.get_active_models()
                    ]

            # ── 7. Auto-summarise memory ─────────────────────────────────
            await memory_manager.auto_summarise(settings.memory_max_rows)

            # ── 8. Self-optimisation ─────────────────────────────────────
            await _self_optimise(state, settings)

            # ── 9. Reflection / safe-mode check ──────────────────────────
            await should_enter_safe_mode(settings.reflection_failure_threshold)

        except Exception as exc:
            logger.error("Scheduler tick error: %s", exc)


async def _self_optimise(state: SystemState, settings: Settings) -> None:
    """
    Apply adaptive behaviour when resources are consistently constrained.
    Logs optimisation decisions to the database.
    """
    is_stressed = state.is_system_stressed(settings)

    # If stressed → reduce monitoring frequency
    if is_stressed and state.monitoring_frequency == "normal":
        state.monitoring_frequency = "reduced"
        await db.insert(
            "optimization_log",
            action="reduce_monitoring",
            reason=f"System stressed (CPU={state.cpu_percent:.0f}%)",
            timestamp=time.time(),
        )
        logger.info("Self-optimisation: monitoring frequency reduced")

    # If no longer stressed → restore normal frequency
    elif not is_stressed and state.monitoring_frequency == "reduced" and state.mode != "idle":
        state.monitoring_frequency = "normal"
        await db.insert(
            "optimization_log",
            action="restore_monitoring",
            reason="Stress resolved",
            timestamp=time.time(),
        )
        logger.info("Self-optimisation: monitoring frequency restored to normal")
