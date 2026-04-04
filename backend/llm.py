"""LLM factory with local Ollama support and Gemini fallback.

Provides a unified interface for non-agentic AI tasks (summaries, cron skills)
that tries a local Ollama model first and falls back to Gemini on failure.
Default local model: gemma4:latest (configurable via OLLAMA_MODEL).
"""

import logging

from langchain_core.messages import BaseMessage, SystemMessage

import config

log = logging.getLogger("homebot.llm")

MIN_RESPONSE_LENGTH = 20


GEMINI_PREFIXES = ("gemini-",)


def is_gemini_model(model: str) -> bool:
    return model.lower().startswith(GEMINI_PREFIXES)


def get_gemini_llm(*, model: str | None = None, **kwargs):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model or config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=kwargs.get("temperature", 0.7),
        max_output_tokens=kwargs.get("max_output_tokens", 2048),
    )


def get_local_llm(*, model: str | None = None, **kwargs):
    if not config.OLLAMA_ENABLED:
        return None
    try:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            base_url=config.OLLAMA_URL,
            model=model or config.OLLAMA_MODEL,
            temperature=kwargs.get("temperature", 0.7),
            num_predict=kwargs.get("num_predict", 1024),
        )
    except Exception as e:
        log.warning("Failed to create local LLM client: %s", e)
        return None


def extract_text(response) -> str:
    """Pull plain text from a LangChain AI message response."""
    raw = response.content
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        return "".join(
            block.get("text", "") for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return ""


def _inject_no_think(messages: list[BaseMessage], model_name: str = "") -> list[BaseMessage]:
    """Append /no_think to the system message for qwen3 models."""
    name = (model_name or config.OLLAMA_MODEL).lower()
    if "qwen3" not in name:
        return messages

    patched = []
    for msg in messages:
        if isinstance(msg, SystemMessage) and not msg.content.endswith("/no_think"):
            patched.append(SystemMessage(content=msg.content + " /no_think"))
        else:
            patched.append(msg)
    return patched


async def invoke_with_fallback(
    messages: list[BaseMessage],
    *,
    model: str | None = None,
    provider: str | None = None,
    prefer_local: bool = True,
    **kwargs,
) -> tuple[str, str]:
    """Invoke an LLM with optional local-first strategy.

    *provider* overrides auto-detection: ``"ollama"`` forces Ollama even for
    model names that look like Gemini (e.g. ``gemini-3-flash-preview`` pulled
    through Ollama Cloud).

    When *model* is set and *provider* is ``None``:
      - A Gemini model name (starts with ``gemini-``) goes straight to Gemini.
      - Anything else is treated as an Ollama model name.
    When *model* is ``None`` the original local-first-then-Gemini fallback is used.

    Returns (text, provider_used) where provider_used is "ollama" or "gemini".
    """
    if model and provider != "ollama" and is_gemini_model(model):
        gemini = get_gemini_llm(model=model, **kwargs)
        response = await gemini.ainvoke(messages)
        text = extract_text(response)
        log.info("Gemini (%s) responded (%d chars)", model, len(text))
        return text, "gemini"

    if model or prefer_local:
        local = get_local_llm(model=model, **kwargs)
        if local:
            try:
                patched = _inject_no_think(messages, model or "")
                response = await local.ainvoke(patched)
                text = extract_text(response)
                if text and len(text) > MIN_RESPONSE_LENGTH:
                    used = model or config.OLLAMA_MODEL
                    log.info("Local LLM (%s) responded (%d chars)", used, len(text))
                    return text, "ollama"
                log.warning("Local LLM returned insufficient response (%d chars), falling back to Gemini", len(text))
            except Exception as e:
                log.warning("Local LLM failed: %s -- falling back to Gemini", e)

    gemini = get_gemini_llm(**kwargs)
    response = await gemini.ainvoke(messages)
    text = extract_text(response)
    log.info("Gemini (%s) responded (%d chars)", config.GEMINI_MODEL, len(text))
    return text, "gemini"
