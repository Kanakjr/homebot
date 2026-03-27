"""Obsidian Brain tools to search and read local markdown files."""

import json
import logging
import os
from pathlib import Path

import config

log = logging.getLogger("deepagent.tools.obsidian")

def _get_vault_path() -> Path:
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        log.warning(f"Obsidian vault path {vault} does not exist.")
    return vault


async def obsidian_search_notes(query: str, limit: int = 10) -> str:
    """Search for a keyword or phrase across all notes in the Obsidian vault.

    Args:
        query: The keyword or phrase to search for.
        limit: Max number of matching files to return (default 10).
    """
    vault = _get_vault_path()
    if not vault.exists():
        return json.dumps({"status": "error", "detail": "Obsidian vault path not found."})

    results = []
    query_lower = query.lower()
    
    try:
        # Simple walk and grep
        for root, _, files in os.walk(vault):
            # Skip hidden directories like .obsidian, .git
            if any(part.startswith('.') for part in Path(root).parts):
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
        log.error(f"Error searching Obsidian notes: {e}")
        return json.dumps({"status": "error", "detail": str(e)})


async def obsidian_read_note(filepath: str) -> str:
    """Read the full content of a specific note from the Obsidian vault.

    Args:
        filepath: The relative path to the markdown file in the vault (e.g. "Ideas/SmartHome.md").
    """
    vault = _get_vault_path()
    path = vault / filepath
    
    # Security: ensure path is within vault
    try:
        path = path.resolve(strict=False)
        vault_resolved = vault.resolve(strict=False)
        if not str(path).startswith(str(vault_resolved)):
            return json.dumps({"status": "error", "detail": "Access restricted to vault directory."})
    except Exception:
        pass
        
    if not path.exists():
        # Try appending .md if they forgot
        path = path.with_suffix(".md")
        if not path.exists():
            return json.dumps({"status": "error", "detail": f"Note '{filepath}' not found."})
            
    try:
        content = path.read_text(encoding="utf-8")
        # truncate if too huge to avoid blowing up context, maybe 15000 chars
        if len(content) > 15000:
            content = content[:15000] + "... [TRUNCATED]"
        return json.dumps({"status": "ok", "filepath": str(path.relative_to(vault)), "content": content})
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)})


async def obsidian_list_directories() -> str:
    """List all top-level folders in the Obsidian vault."""
    vault = _get_vault_path()
    if not vault.exists():
        return json.dumps({"status": "error", "detail": "Obsidian vault path not found."})
        
    try:
        dirs = [d.name for d in vault.iterdir() if d.is_dir() and not d.name.startswith('.')]
        return json.dumps({"status": "ok", "directories": dirs})
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)})


def get_obsidian_tools() -> list:
    """Return all Obsidian tools."""
    return [obsidian_search_notes, obsidian_read_note, obsidian_list_directories]
