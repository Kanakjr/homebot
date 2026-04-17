"""Lightweight AI skill executor that calls Ollama directly.

Instead of routing through the Deep Agent (which loads 57 tools and
overwhelms small models), this module calls Ollama's /api/chat endpoint
with a compact system prompt, the persona, and the live HA state summary.
"""

import json
import logging
from pathlib import Path

import aiohttp

import config

log = logging.getLogger("homebot.skill_runner")

_PERSONA_PATH = Path("/app/persona.md")

_SYSTEM_PROMPT = """\
{persona}
You are also a smart home assistant powered by Home Assistant.
The home is in India (IST timezone). Residents: Kanak and Sarath.

You are executing an automated skill. The result will be sent as a notification.
Format with emojis, clear sections, warm tone. Be concise (4-8 lines).
Avoid raw markdown syntax like ** or ##. Use emojis and line breaks instead.
Keep it easy to scan at a glance.

Below is the CURRENT live state of the home and recent events.
Use this data to answer -- do NOT make up values or say "I don't have access".
"""


def _load_persona() -> str:
    try:
        return _PERSONA_PATH.read_text().strip()
    except FileNotFoundError:
        return "You are a helpful smart home assistant."


async def run_skill(
    skill_name: str,
    ai_prompt: str,
    state_summary: str,
    event_log_text: str,
) -> str:
    """Execute an AI skill prompt against Ollama and return the response text."""
    persona = _load_persona()
    system = _SYSTEM_PROMPT.format(persona=persona)

    user_msg = f"[SKILL: {skill_name}]\n\n{ai_prompt}"
    if state_summary:
        user_msg += f"\n\n--- Current Home State ---\n{state_summary}"
    if event_log_text:
        user_msg += f"\n\n--- Recent Events (24h) ---\n{event_log_text}"

    payload = {
        "model": config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 512},
    }

    url = f"{config.OLLAMA_URL}/api/chat"
    log.info("Skill '%s' -> Ollama %s (model=%s)", skill_name, url, config.OLLAMA_MODEL)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.error("Ollama returned %s: %s", resp.status, body[:300])
                return f"Skill '{skill_name}' failed: Ollama error ({resp.status})"

            data = await resp.json()
            text = data.get("message", {}).get("content", "").strip()

            tokens = data.get("eval_count", 0)
            duration_ms = data.get("total_duration", 0) / 1e6
            log.info(
                "Skill '%s' done: %d tokens in %.1fs",
                skill_name, tokens, duration_ms / 1000,
            )

            return text or f"Skill '{skill_name}' completed but returned empty."
