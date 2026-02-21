"""
main.py — FastAPI application for Friday Phase 3.

Endpoints:
  GET  /health-check       → extended health check
  GET  /system-status      → CPU / RAM / disk / GPU snapshot
  GET  /system-state       → full state (mode, stress, models, tasks)
  GET  /mode               → current operating mode
  POST /switch-mode        → change operating mode
  POST /chat               → context-aware conversation
  POST /execute            → natural-language → 4-layer safety chain → safe execution
  GET  /logs               → last 20 log entries
  
  Phase 3 Endpoints:
  GET  /memory             → recent conversations & tasks
  POST /clear-memory       → wipe conversation & task history
  GET  /memory-summary     → counts for memory tables
  GET  /patterns           → detected usage patterns
  GET  /reflection-status  → failure count, safe-mode flag
  GET  /suggestions        → proactive suggestions
  GET  /personality        → current personality trait
  POST /personality        → set personality trait
  POST /safe-mode          → force-enable/disable safe mode
"""

import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app import database as db
from app import memory_manager
from app import pattern_engine
from app import reflection_engine
from app import proactive_engine
from app.personality import get_personality, set_personality
from app.brain import chat as brain_chat
from app.config_loader import Settings, load_settings
from app.executor import execute_instruction
from app.logger_setup import setup_logging
from app.model_controller import ModelController
from app.monitor import get_system_status
from app.scheduler import autonomous_loop
from app.state_manager import SystemState

# ── Application state (populated in lifespan) ────────────────────────────────
settings: Settings = Settings()
system_state: SystemState = SystemState()
model_ctrl: ModelController = ModelController()
_scheduler_task: asyncio.Task | None = None

_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "friday.log"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global settings, system_state, model_ctrl, _scheduler_task

    setup_logging()
    settings = load_settings()
    system_state = SystemState()
    model_ctrl = ModelController()

    logger = logging.getLogger(__name__)
    logger.info("🟢 Friday Phase 3 starting up")
    
    # Init Database
    await db.init_db(settings.db_path)
    
    logger.info("   Model        : %s", settings.openrouter_model)
    logger.info("   Language      : %s", settings.language)
    logger.info("   Personality   : %s", settings.personality)
    logger.info(
        "   API key       : %s",
        "configured ✔" if settings.openrouter_api_key else "MISSING ✘",
    )

    # Load the default model into the controller
    model_ctrl.load_model(settings.openrouter_model)

    # Initial system state refresh
    await system_state.refresh()

    # Set default personality from config
    set_personality(settings.personality)

    # Background autonomous loop (replaces idle_check_loop)
    _scheduler_task = asyncio.create_task(autonomous_loop(system_state, settings, model_ctrl))

    yield  # ── app is running ──

    # Shutdown
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass

    await db.close_db()
    logger.info("🔴 Friday Phase 3 shutting down")


app = FastAPI(
    title="Friday — Phase 3",
    description="Autonomous self-optimizing AI assistant backend",
    version="0.3.0",
    lifespan=lifespan,
)


# ── Request / Response schemas ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message for Friday")


class ChatResponse(BaseModel):
    reply: str


class ExecuteRequest(BaseModel):
    instruction: str = Field(..., min_length=1, description="Natural-language instruction")


class ExecuteResponse(BaseModel):
    status: str
    command: str | None = None
    risk_level: str | None = None
    decision: dict | None = None
    output: str | None = None
    error: str | None = None


class SwitchModeRequest(BaseModel):
    mode: str = Field(..., description="Target mode: idle, monitor, coding, voice, heavy")


class PersonalityRequest(BaseModel):
    personality: str = Field(..., description="Trait: professional, friendly, sarcastic, productivity_coach")


class SafeModeRequest(BaseModel):
    enabled: bool = Field(..., description="Enable or disable safe mode manually")


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health-check")
async def health_check():
    """Extended health check with mode and stress info."""
    await system_state.refresh()
    return {
        "status": "ok",
        "mode": system_state.mode,
        "is_stressed": system_state.is_system_stressed(settings),
        "active_models": model_ctrl.get_active_models(),
    }


@app.get("/health")
async def health():
    """Simple health check (Phase 1 compat)."""
    return {"status": "ok"}


@app.get("/system-status")
async def system_status():
    """Return a raw snapshot of CPU, RAM, disk, and GPU usage."""
    return await get_system_status()


@app.get("/system-state")
async def system_state_endpoint():
    """Full system state: mode, stress, models, tasks, resource levels."""
    await system_state.refresh()

    # Auto-unload stale models if enabled
    if settings.auto_unload:
        unloaded = model_ctrl.auto_unload_check(settings.model_unload_timeout_minutes)
        if unloaded:
            system_state.loaded_models = [
                m["name"] for m in model_ctrl.get_active_models()
            ]

    # Sync loaded models list into state
    system_state.loaded_models = [m["name"] for m in model_ctrl.get_active_models()]

    return system_state.snapshot(settings)


@app.get("/mode")
async def get_mode():
    """Return the current operating mode."""
    return {"mode": system_state.mode}


@app.post("/switch-mode")
async def switch_mode(req: SwitchModeRequest):
    """Switch Friday's operating mode."""
    result = system_state.switch_mode(req.mode)
    
    # Record mode switch pattern
    if result["status"] == "ok":
        await pattern_engine.record_action("mode_switch", req.mode)
        
    return result


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to Friday and get an LLM-powered reply."""
    
    # Wake up if idle
    system_state.wake()
    system_state.touch()
    
    model_ctrl.touch_model(settings.openrouter_model)
    
    # Store user message
    await memory_manager.store_conversation("user", req.message)
    
    # Prep context
    context = await memory_manager.get_context_messages(6)
    state_summary = (
        f"Mode: {system_state.mode}, "
        f"Stressed: {system_state.is_system_stressed(settings)}, "
        f"CPU: {system_state.cpu_percent}%, "
        f"RAM free: {system_state.ram_available_mb}MB"
    )
    
    # Get reply
    reply = await brain_chat(req.message, settings, context, state_summary)
    
    # Store assistant reply
    await memory_manager.store_conversation("assistant", reply)
    
    return ChatResponse(reply=reply)


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    """
    Convert a natural-language instruction to a command, run it through the
    decision engine, and execute if approved. Uses the 4-layer Phase 3 safety chain.
    """
    system_state.wake()
    system_state.touch()
    result = await execute_instruction(req.instruction, settings, system_state)
    return ExecuteResponse(**result)


@app.get("/logs")
async def get_logs(count: int = 20):
    """Return the last N log entries from friday.log."""
    if not _LOG_FILE.exists():
        return {"logs": [], "message": "No log file found yet."}

    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as fh:
            all_lines = fh.readlines()
        recent = [line.strip() for line in all_lines[-count:] if line.strip()]
        return {"logs": recent, "total": len(all_lines)}
    except Exception as exc:
        return {"logs": [], "error": str(exc)}

# ── Phase 3 Endpoints ────────────────────────────────────────────────────────

@app.get("/memory")
async def get_memory():
    """Return recent conversations and tasks from SQLite."""
    return {
        "recent_conversations": await memory_manager.get_recent_conversations(10),
        "recent_tasks": await memory_manager.get_recent_tasks(10),
    }

@app.get("/memory-summary")
async def get_memory_summary():
    """Return counts for tables in SQLite."""
    return await memory_manager.get_memory_summary()

@app.post("/clear-memory")
async def clear_memory():
    """Wipe conversations and tasks."""
    return await memory_manager.clear_memory()

@app.get("/patterns")
async def get_patterns():
    """Return detected usage patterns."""
    return {
        "top_commands": await pattern_engine.get_top_commands(10),
        "top_apps": await pattern_engine.get_top_apps(10),
        "time_clusters": await pattern_engine.get_time_clusters()
    }

@app.get("/reflection-status")
async def get_reflection_status():
    """Return failure count and safe-mode flag."""
    return await reflection_engine.get_reflection_status()

@app.get("/suggestions")
async def get_suggestions():
    """Return proactive suggestions."""
    return {"suggestions": proactive_engine.get_cached_suggestions()}

@app.get("/personality")
async def get_personality_endpoint():
    """Return current personality trait."""
    return {"personality": get_personality()}

@app.post("/personality")
async def set_personality_endpoint(req: PersonalityRequest):
    """Set personality trait."""
    return set_personality(req.personality)

@app.post("/safe-mode")
async def safe_mode(req: SafeModeRequest):
    """Force-enable/disable safe mode."""
    return reflection_engine.set_safe_mode(req.enabled)

