"""Long-term memory: read/write/search markdown under Obsidian vault homebot-brain only."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import config

log = logging.getLogger("deepagent.tools.memory")


def _brain_root() -> Path:
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    sub = config.HOMEBOT_BRAIN_SUBDIR.strip().strip("/").replace("\\", "/")
    return vault / sub


def _resolve_safe_relative(relative_path: str) -> tuple[Path | None, str | None]:
    """Return (absolute_path_under_brain, error_json_detail) or (None, error)."""
    if not relative_path or relative_path.strip() == "":
        return None, "relative_path is required"
    rel = Path(relative_path)
    if rel.is_absolute():
        return None, "path must be relative to the brain folder"
    brain = _brain_root()
    try:
        candidate = (brain / rel).resolve()
        brain_resolved = brain.resolve(strict=False)
    except OSError as e:
        return None, str(e)
    if not str(candidate).startswith(str(brain_resolved)):
        return None, "path escapes brain directory"
    return candidate, None


async def memory_list_notes() -> str:
    """List all markdown files under the long-term memory folder (recursive), paths relative to that folder."""
    brain = _brain_root()
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        return json.dumps({"status": "error", "detail": "Obsidian vault path not found."})
    if not brain.exists():
        return json.dumps({"status": "ok", "notes": [], "brain": str(brain), "hint": "folder empty or not created yet"})

    notes: list[str] = []
    try:
        for root, _, files in os.walk(brain):
            if any(part.startswith(".") for part in Path(root).parts):
                continue
            for file in files:
                if not file.endswith(".md"):
                    continue
                full = Path(root) / file
                rel = full.relative_to(brain)
                notes.append(str(rel).replace("\\", "/"))
        notes.sort()
        return json.dumps({"status": "ok", "notes": notes, "brain_root": str(brain)})
    except Exception as e:
        log.error("memory_list_notes: %s", e)
        return json.dumps({"status": "error", "detail": str(e)})


async def memory_read_note(relative_path: str) -> str:
    """Read one markdown file from long-term memory. Path is relative to the brain folder (e.g. preferences.md)."""
    path, err = _resolve_safe_relative(relative_path)
    if err:
        return json.dumps({"status": "error", "detail": err})
    brain = _brain_root()
    if not path.exists():
        alt = path.with_suffix(".md") if path.suffix != ".md" else path
        if alt.exists():
            path = alt
        else:
            return json.dumps({"status": "error", "detail": f"Note not found: {relative_path}"})

    try:
        content = path.read_text(encoding="utf-8")
        if len(content) > 15000:
            content = content[:15000] + "... [TRUNCATED]"
        rel = path.relative_to(brain)
        return json.dumps(
            {"status": "ok", "filepath": str(rel).replace("\\", "/"), "content": content}
        )
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)})


async def memory_search_notes(query: str, limit: int = 20) -> str:
    """Search for a keyword or phrase only inside the long-term memory folder."""
    brain = _brain_root()
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        return json.dumps({"status": "error", "detail": "Obsidian vault path not found."})
    if not brain.exists():
        return json.dumps({"status": "ok", "results": [], "query": query})

    results: list[str] = []
    query_lower = query.lower()
    try:
        for root, _, files in os.walk(brain):
            if any(part.startswith(".") for part in Path(root).parts):
                continue
            for file in files:
                if not file.endswith(".md"):
                    continue
                path = Path(root) / file
                rel = path.relative_to(brain)
                try:
                    text = path.read_text(encoding="utf-8").lower()
                except (UnicodeDecodeError, OSError):
                    continue
                if query_lower in text or query_lower in file.lower():
                    results.append(str(rel).replace("\\", "/"))
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break
        return json.dumps({"status": "ok", "results": results, "query": query})
    except Exception as e:
        log.error("memory_search_notes: %s", e)
        return json.dumps({"status": "error", "detail": str(e)})


async def memory_write_note(relative_path: str, content: str, append: bool = False) -> str:
    """Create or update a markdown file under long-term memory. Set append=true to append (with optional timestamp line)."""
    path, err = _resolve_safe_relative(relative_path)
    if err:
        return json.dumps({"status": "error", "detail": err})
    brain = _brain_root()
    try:
        brain.mkdir(parents=True, exist_ok=True)
        if path.suffix != ".md" and not path.exists():
            path = path.with_suffix(".md")

        if append and path.exists():
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            block = f"\n\n---\n*Append {ts}*\n\n{content}"
            with path.open("a", encoding="utf-8") as f:
                f.write(block)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        rel = path.relative_to(brain)
        return json.dumps(
            {
                "status": "ok",
                "filepath": str(rel).replace("\\", "/"),
                "append": append,
            }
        )
    except Exception as e:
        log.error("memory_write_note: %s", e)
        return json.dumps({"status": "error", "detail": str(e)})


def get_memory_tools() -> list:
    return [
        memory_list_notes,
        memory_read_note,
        memory_search_notes,
        memory_write_note,
    ]
