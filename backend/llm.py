"""LLM factory with local Ollama support and Gemini fallback.

Provides a unified interface for "lazy" AI tasks (summaries, cron skills)
that tries a local Ollama model first and falls back to Gemini on failure.
"""

import logging

from langchain_core.messages import BaseMessage, SystemMessage

import config

log = logging.getLogger("homebot.llm")

MIN_RESPONSE_LENGTH = 20


def get_gemini_llm(**kwargs):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=kwargs.get("temperature", 0.7),
        max_output_tokens=kwargs.get("max_output_tokens", 2048),
    )


def get_local_llm(**kwargs):
    if not config.OLLAMA_ENABLED:
        return None
    try:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            base_url=config.OLLAMA_URL,
            model=config.OLLAMA_MODEL,
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


def _inject_no_think(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Append /no_think to the system message for qwen3 models."""
    if "qwen3" not in config.OLLAMA_MODEL.lower():
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
    prefer_local: bool = True,
    **kwargs,
) -> tuple[str, str]:
    """Invoke an LLM with optional local-first strategy.

    Returns (text, provider) where provider is "ollama" or "gemini".
    """
    if prefer_local:
        local = get_local_llm(**kwargs)
        if local:
            try:
                patched = _inject_no_think(messages)
                response = await local.ainvoke(patched)
                text = extract_text(response)
                if text and len(text) > MIN_RESPONSE_LENGTH:
                    log.info("Local LLM (%s) responded (%d chars)", config.OLLAMA_MODEL, len(text))
                    return text, "ollama"
                log.warning("Local LLM returned insufficient response (%d chars), falling back to Gemini", len(text))
            except Exception as e:
                log.warning("Local LLM failed: %s -- falling back to Gemini", e)

    gemini = get_gemini_llm(**kwargs)
    response = await gemini.ainvoke(messages)
    text = extract_text(response)
    log.info("Gemini (%s) responded (%d chars)", config.GEMINI_MODEL, len(text))
    return text, "gemini"
