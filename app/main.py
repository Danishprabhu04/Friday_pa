"""
main.py — FastAPI application for Friday Phase 1.

Endpoints:
  GET  /health          → health check
  GET  /system-status   → CPU / RAM / disk / GPU snapshot
  POST /chat            → general LLM conversation
  POST /execute         → natural-language → safe command execution
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.brain import chat as brain_chat
from app.config_loader import Settings, load_settings
from app.executor import execute_instruction
from app.logger_setup import setup_logging
from app.monitor import get_system_status

# ── Application state ────────────────────────────────────────────────────────
settings: Settings = Settings()  # replaced at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global settings

    setup_logging()
    settings = load_settings()

    logger = logging.getLogger(__name__)
    logger.info("🟢 Friday Phase 1 starting up")
    logger.info("   Model  : %s", settings.openrouter_model)
    logger.info("   Language: %s", settings.language)
    logger.info(
        "   API key : %s",
        "configured ✔" if settings.openrouter_api_key else "MISSING ✘",
    )

    yield  # ── app is running ──

    logger.info("🔴 Friday Phase 1 shutting down")


app = FastAPI(
    title="Friday — Phase 1",
    description="Controlled AI assistant backend",
    version="0.1.0",
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
    output: str | None = None
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok"}


@app.get("/system-status")
async def system_status():
    """Return a snapshot of CPU, RAM, disk, and GPU usage."""
    return await get_system_status()


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to Friday and get an LLM-powered reply."""
    reply = await brain_chat(req.message, settings)
    return ChatResponse(reply=reply)


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    """Convert a natural-language instruction to a command and execute it safely."""
    result = await execute_instruction(req.instruction, settings)
    return ExecuteResponse(**result)
