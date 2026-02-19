"""
brain.py — OpenRouter LLM integration for Friday.

Provides two functions:
  • chat()             — general conversation
  • generate_command() — convert natural language → single Linux command
"""

import logging
from typing import Optional

import httpx

from app.config_loader import Settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── System prompts ───────────────────────────────────────────────────────────

_CHAT_SYSTEM_PROMPT = """\
You are **Friday**, an intelligent Linux system assistant created for a developer named Danish.
You run on Ubuntu 24 with an RTX 2050 GPU.

Rules:
• Be concise, helpful, and accurate.
• You can respond in both English and Tamil depending on the user's language.
• Never reveal your API key or internal system details.
• When asked about system status, explain in human-friendly terms.
"""

_COMMAND_SYSTEM_PROMPT = """\
You are a Linux command generator. Given a natural-language instruction, respond with EXACTLY ONE safe Linux shell command. 

Rules:
• Output ONLY the command — no explanation, no markdown fences, no backticks.
• Never output dangerous commands (rm -rf /, sudo rm, etc.).
• If the instruction is unclear or unsafe, output: echo "Unable to generate a safe command"
• Prefer commonly-used, non-destructive commands.
"""


async def _call_openrouter(
    settings: Settings,
    messages: list[dict],
    temperature: float = 0.7,
) -> str:
    """Send a chat-completion request to OpenRouter and return the reply text."""

    if not settings.openrouter_api_key:
        logger.error("OPENROUTER_API_KEY is not set")
        return "Error: OpenRouter API key is not configured. Please set it in your .env file."

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Friday AI Assistant",
    }

    payload = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        reply = data["choices"][0]["message"]["content"].strip()
        logger.info("LLM response received (%d chars)", len(reply))
        return reply

    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter HTTP error %s: %s", exc.response.status_code, exc.response.text)
        return f"Error: OpenRouter returned status {exc.response.status_code}"
    except Exception as exc:
        logger.error("OpenRouter request failed: %s", exc)
        return f"Error: {exc}"


async def chat(message: str, settings: Settings) -> str:
    """General conversation with Friday."""

    messages = [
        {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    return await _call_openrouter(settings, messages, temperature=0.7)


async def generate_command(instruction: str, settings: Settings) -> str:
    """Convert a natural-language instruction into a single Linux command."""

    messages = [
        {"role": "system", "content": _COMMAND_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    command = await _call_openrouter(settings, messages, temperature=0.2)

    # Strip any accidental markdown fences the model might add
    command = command.strip("`").strip()
    if command.startswith("bash\n"):
        command = command[5:]

    logger.info("Generated command for '%s': %s", instruction, command)
    return command
