"""Shared test configuration: model registry, LLM factory, and timing helpers."""

import sys
import time
from pathlib import Path

# Ensure the backend package is importable from any test location.
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import config  # noqa: E402

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, dict] = {
    "gemini-2.5-flash": {
        "provider": "gemini",
        "model": config.GEMINI_MODEL,
    },
    "qwen3.5:9b": {
        "provider": "ollama",
        "model": "qwen3.5:9b",
    },
    "qwen3.5:4b": {
        "provider": "ollama",
        "model": "qwen3.5:4b",
    },
    "qwen3.5:2b": {
        "provider": "ollama",
        "model": "qwen3.5:2b",
    },
    "sorc/qwen3.5-claude-4.6-opus-q4:9b": {
        "provider": "ollama",
        "model": "sorc/qwen3.5-claude-4.6-opus-q4:9b",
    },
    "sorc/qwen3.5-claude-4.6-opus-q4:4b": {
        "provider": "ollama",
        "model": "sorc/qwen3.5-claude-4.6-opus-q4:4b",
    },
    "sorc/qwen3.5-claude-4.6-opus-q4:2b": {
        "provider": "ollama",
        "model": "sorc/qwen3.5-claude-4.6-opus-q4:2b",
    },
    "gemma4:e2b": {
        "provider": "ollama",
        "model": "gemma4:e2b",
    },
    "gemma4:latest": {
        "provider": "ollama",
        "model": "gemma4:latest",
    },
    "homebot-qwen3_5-2b": {
        "provider": "ollama",
        "model": "homebot-qwen3_5-2b",
    },
    "homebot-qwen3_5-4b": {
        "provider": "ollama",
        "model": "homebot-qwen3_5-4b",
    },
}

_config_url = getattr(config, "OLLAMA_URL", "http://localhost:11434")
OLLAMA_URL = _config_url.replace("host.docker.internal", "localhost")


def get_llm(model_key: str, **kwargs):
    """Return a LangChain BaseChatModel for the given registry key.

    Raises KeyError if the key is not in the registry.
    Raises RuntimeError if the provider is unavailable.
    """
    entry = MODEL_REGISTRY[model_key]
    provider = entry["provider"]
    model_name = entry["model"]

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=config.GEMINI_API_KEY,
            temperature=kwargs.get("temperature", 0.3),
            max_output_tokens=kwargs.get("max_output_tokens", 2048),
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            base_url=OLLAMA_URL,
            model=model_name,
            temperature=kwargs.get("temperature", 0.3),
            num_predict=kwargs.get("num_predict", 1024),
        )

    raise RuntimeError(f"Unknown provider: {provider}")


async def is_model_available(model_key: str) -> bool:
    """Check whether a model is reachable (Ollama downloaded, Gemini key set)."""
    entry = MODEL_REGISTRY[model_key]

    if entry["provider"] == "gemini":
        return bool(config.GEMINI_API_KEY)

    if entry["provider"] == "ollama":
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{OLLAMA_URL}/api/show",
                    json={"name": entry["model"]},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    return False


async def preload_model(model_key: str) -> bool:
    """Warm up an Ollama model by sending an empty generate request.

    Forces the model weights into VRAM/RAM before the first real request
    so that cold-load time does not skew benchmark results.
    Returns True if the preload succeeded, False otherwise.
    Gemini models are skipped (always warm on the server side).
    """
    entry = MODEL_REGISTRY[model_key]
    if entry["provider"] != "ollama":
        return True

    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": entry["model"], "prompt": "", "stream": False},
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def unload_model(model_key: str) -> bool:
    """Unload an Ollama model from VRAM/RAM immediately.

    Equivalent to ``ollama stop <model>``.  Uses ``keep_alive: 0`` to
    tell Ollama to evict the model as soon as the request completes.
    """
    entry = MODEL_REGISTRY[model_key]
    if entry["provider"] != "ollama":
        return True

    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": entry["model"], "prompt": "", "keep_alive": 0, "stream": False},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def unload_all_models() -> None:
    """Unload every Ollama model in the registry to start with clean VRAM."""
    for key, entry in MODEL_REGISTRY.items():
        if entry["provider"] == "ollama":
            await unload_model(key)


class Timer:
    """Simple wall-clock timer context manager."""

    def __init__(self):
        self.start = 0.0
        self.elapsed_ms = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
