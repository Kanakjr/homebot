"""Obsidian vault tools for the main HomeBotAI backend (LangChain BaseTool format)."""

import json
import logging
import os
from pathlib import Path

from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.obsidian")


def _vault() -> Path:
    path = Path(config.OBSIDIAN_VAULT_PATH)
    if not path.exists():
        log.warning("Obsidian vault not found at %s", path)
    return path


@tool
async def obsidian_search_notes(query: str, limit: int = 10) -> str:
    """Search for a keyword or phrase across all notes in the Obsidian vault.

    Args:
        query: The keyword or phrase to search for.
        limit: Max number of matching files to return (default 10).
    """
    vault = _vault()
    if not vault.exists():
        return json.dumps({"status": "error", "detail": "Obsidian vault path not found."})

    results = []
    query_lower = query.lower()
    try:
        for root, _, files in os.walk(vault):
            if any(part.startswith(".") for part in Path(root).parts):
                continue
            for file in files:
                if not file.endswith(".md"):
                    continue
                path = Path(root) / file
                rel_path = path.relative_to(vault)
                try:
                    content = path.read_text(encoding="utf-8").lower()
                    if query_lower in content or query_lower in file.lower():
                        results.append(str(rel_path))
                        if len(results) >= limit:
                            break
                except UnicodeDecodeError:
                    continue
            if len(results) >= limit:
                break
        return json.dumps({"status": "ok", "results": results, "query": query})
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)})


@tool
async def obsidian_read_note(filepath: str) -> str:
    """Read the full content of a specific note from the Obsidian vault.

    Args:
        filepath: Relative path to the markdown file in the vault (e.g. 'Ideas/SmartHome.md').
    """
    vault = _vault()
    path = (vault / filepath).resolve()
    if not str(path).startswith(str(vault.resolve())):
        return json.dumps({"status": "error", "detail": "Access restricted to vault directory."})
    if not path.exists():
        path = path.with_suffix(".md")
        if not path.exists():
            return json.dumps({"status": "error", "detail": f"Note '{filepath}' not found."})
    try:
        content = path.read_text(encoding="utf-8")
        if len(content) > 15000:
            content = content[:15000] + "... [TRUNCATED]"
        return json.dumps({"status": "ok", "filepath": str(path.relative_to(vault)), "content": content})
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)})


@tool
async def obsidian_list_directories() -> str:
    """List all top-level folders in the Obsidian vault."""
    vault = _vault()
    if not vault.exists():
        return json.dumps({"status": "error", "detail": "Obsidian vault path not found."})
    try:
        dirs = [d.name for d in vault.iterdir() if d.is_dir() and not d.name.startswith(".")]
        return json.dumps({"status": "ok", "directories": dirs})
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)})


def create_obsidian_tools() -> list:
    return [obsidian_search_notes, obsidian_read_note, obsidian_list_directories]
