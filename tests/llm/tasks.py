"""Benchmark task definitions and validation helpers.

Each task is a dict with:
  - id: str           unique slug
  - name: str         human label
  - system: str       optional system prompt
  - prompt: str       user message
  - validate(text) -> (bool, str)   returns (passed, detail)
"""

import json
import re

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _has_min_length(text: str, n: int = 20) -> tuple[bool, str]:
    if len(text.strip()) >= n:
        return True, f"{len(text)} chars"
    return False, f"Too short ({len(text)} chars, need {n})"


def _is_valid_json(text: str) -> tuple[bool, dict | None]:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if match:
        cleaned = match.group(1).strip()
    try:
        data = json.loads(cleaned)
        return True, data
    except json.JSONDecodeError as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------


TASKS: list[dict] = [
    {
        "id": "basic_chat",
        "name": "Basic Chat",
        "system": "You are a helpful smart-home assistant.",
        "prompt": "Explain what a smart home is in exactly 2 sentences.",
        "validate": lambda text: (
            _has_min_length(text, 30)[0]
            and 1 <= text.count(".") <= 5,
            f"{'PASS' if _has_min_length(text, 30)[0] else 'Too short'}; "
            f"sentences={text.count('.')}",
        ),
    },
    {
        "id": "ha_parsing",
        "name": "Home Automation Parsing",
        "system": (
            "You are a home automation parser. Extract the user intent as JSON "
            "with keys: entity, action, parameters. Return ONLY valid JSON, "
            "no extra text."
        ),
        "prompt": "Turn on the bedroom light to 50% brightness",
        "validate": lambda text: _validate_ha_parsing(text),
    },
    {
        "id": "json_structured",
        "name": "JSON Structured Output",
        "system": (
            "Respond ONLY with valid JSON. No markdown fences, no commentary."
        ),
        "prompt": (
            "List 3 popular programming languages with their primary use case. "
            'Format: [{"language": "...", "use_case": "..."}]'
        ),
        "validate": lambda text: _validate_json_list(text),
    },
    {
        "id": "summarization",
        "name": "Summarization",
        "system": "Summarize the following text in exactly one sentence.",
        "prompt": (
            "Home automation is the automatic control of electronic devices in "
            "your home. These devices are connected to the Internet, which allows "
            "them to be controlled remotely. With home automation, devices can "
            "trigger one another and you don't have to control them manually via "
            "an app or voice assistant. For example, you can put your lights on "
            "schedules so that they turn off when you normally go to sleep, or "
            "you can have your thermostat turn the AC up about an hour before "
            "you come back from work so that you don't have to come home to a "
            "stuffy house."
        ),
        "validate": lambda text: (
            _has_min_length(text, 20)[0]
            and len(text.split()) <= 80,
            f"words={len(text.split())}; {_has_min_length(text, 20)[1]}",
        ),
    },
    {
        "id": "media_query",
        "name": "Media Query Understanding",
        "system": (
            "You are a media search assistant. Extract search parameters as JSON "
            "with keys: genre, year, quality (optional), sort_by (optional). "
            "Return ONLY valid JSON."
        ),
        "prompt": "Find action movies from 2024 with good ratings",
        "validate": lambda text: _validate_media_query(text),
    },
    {
        "id": "skill_prompt",
        "name": "Skill Prompt Execution",
        "system": (
            "You are HomeBotAI. Given the current home state, answer the user. "
            "State: bedroom light OFF, living room light ON (warm white 60%), "
            "temperature 24C, humidity 45%."
        ),
        "prompt": "Give me a quick status report of all devices.",
        "validate": lambda text: (
            _has_min_length(text, 40)[0]
            and any(kw in text.lower() for kw in ["bedroom", "living", "light"]),
            f"Contains device refs: "
            f"{'yes' if any(kw in text.lower() for kw in ['bedroom', 'living', 'light']) else 'no'}; "
            f"{_has_min_length(text, 40)[1]}",
        ),
    },
]


def _validate_ha_parsing(text: str) -> tuple[bool, str]:
    ok, data = _is_valid_json(text)
    if not ok:
        return False, f"Invalid JSON: {data}"
    if not isinstance(data, dict):
        return False, f"Expected object, got {type(data).__name__}"
    required = {"entity", "action"}
    missing = required - set(data.keys())
    if missing:
        return False, f"Missing keys: {missing}"
    return True, f"keys={list(data.keys())}"


def _validate_json_list(text: str) -> tuple[bool, str]:
    ok, data = _is_valid_json(text)
    if not ok:
        return False, f"Invalid JSON: {data}"
    if not isinstance(data, list):
        return False, f"Expected list, got {type(data).__name__}"
    if len(data) < 2:
        return False, f"Only {len(data)} items"
    for item in data:
        if not isinstance(item, dict):
            return False, f"Item is {type(item).__name__}, expected object"
        if "language" not in item:
            return False, f"Missing 'language' key in {item}"
    return True, f"{len(data)} items"


def _validate_media_query(text: str) -> tuple[bool, str]:
    ok, data = _is_valid_json(text)
    if not ok:
        return False, f"Invalid JSON: {data}"
    if not isinstance(data, dict):
        return False, f"Expected object, got {type(data).__name__}"
    if "genre" not in data:
        return False, f"Missing 'genre' key; got keys={list(data.keys())}"
    return True, f"keys={list(data.keys())}, genre={data.get('genre')}"


def get_task(task_id: str) -> dict:
    """Look up a task by id. Raises KeyError if not found."""
    for t in TASKS:
        if t["id"] == task_id:
            return t
    raise KeyError(f"Unknown task: {task_id}")
