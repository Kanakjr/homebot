"""Model eligibility policy for Deep Agent.

Qwen-family models above a configurable parameter threshold are excluded
from the Deep Agent picker to keep agent quality high on resource-constrained
hardware. Non-Qwen models (including cloud-backed Ollama tags like
gemini-3-flash-preview) pass through unconditionally.
"""

import re

import config

_SIZE_RE = re.compile(r":(\d+)b\b", re.IGNORECASE)
_QWEN_RE = re.compile(r"qwen", re.IGNORECASE)


def _max_qwen_b() -> int:
    return getattr(config, "DEEPAGENT_MAX_QWEN_B", 4)


def ollama_name_eligible_for_deepagent(name: str) -> bool:
    """Return True if an Ollama model name is allowed in the Deep Agent picker.

    Qwen-family models whose tag indicates a parameter count above
    DEEPAGENT_MAX_QWEN_B (default 4) are excluded.  Non-Qwen models and
    Qwen models without a parseable size tag are always eligible.
    """
    if not _QWEN_RE.search(name):
        return True

    match = _SIZE_RE.search(name)
    if not match:
        return True

    size = int(match.group(1))
    return size <= _max_qwen_b()


def ollama_id_eligible_for_deepagent(ollama_id: str) -> bool:
    """Same check but accepts the ``ollama:name`` id format used by the API."""
    name = ollama_id.split(":", 1)[1] if ollama_id.startswith("ollama:") else ollama_id
    return ollama_name_eligible_for_deepagent(name)
