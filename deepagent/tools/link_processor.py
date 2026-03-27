"""Link processing tools to fetch content and save it to Obsidian vault."""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import config

log = logging.getLogger("deepagent.tools.link_processor")

def _get_vault_path() -> Path:
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        vault.mkdir(parents=True, exist_ok=True)
    return vault

def _clean_filename(title: str) -> str:
    return re.sub(r'[^\w\s-]', '', title).strip()[:50]

async def process_and_save_link(url: str, category: str = "Bookmarks", tags: str = "") -> str:
    """Fetch content/metadata from a URL and save it as a markdown note in the Obsidian vault.
    
    Args:
        url: The Instagram, YouTube, or web article URL.
        category: A folder name in the vault to save to (e.g. 'Bookmarks', 'Recipes').
        tags: Optional comma-separated string of tags (e.g. 'youtube,music').
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    vault = _get_vault_path()
    category_path = vault / category
    category_path.mkdir(parents=True, exist_ok=True)
    
    domain = urlparse(url).netloc.lower()
    is_media = any(d in domain for d in ['youtube.com', 'youtu.be', 'instagram.com', 'twitter.com', 'x.com', 'tiktok.com'])
    
    title = "Untitled Link"
    content = ""
    author = ""
    
    if is_media:
        # Use yt-dlp to get metadata
        try:
            # --dump-json prints the video info
            result = subprocess.run(
                ["yt-dlp", "--dump-json", "--no-warnings", url],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                # yt-dlp returns one JSON object per video
                data = json.loads(result.stdout.strip().split('\n')[0])
                title = data.get("title", title)
                description = data.get("description", "")
                uploader = data.get("uploader", "")
                
                content = f"**Uploader**: {uploader}\n\n**Description**:\n{description}\n"
            else:
                log.error(f"yt-dlp error: {result.stderr}")
                content = f"Could not fetch media metadata.\n\nError: {result.stderr}"
        except Exception as e:
            content = f"Failed to run yt-dlp: {e}\n(Make sure yt-dlp is installed in the environment)"
    else:
        # Fallback to simple HTML fetch for title
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')
                match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                if match:
                    title = match.group(1).strip()
                content = "Article parsed. (Detailed text extraction not implemented yet)."
        except Exception as e:
            content = f"Failed to fetch webpage: {e}"

    # Build Markdown note
    safe_title = _clean_filename(title) or "Saved_Link"
    filename = f"{safe_title}.md"
    filepath = category_path / filename
    
    # Handle duplicates
    counter = 1
    while filepath.exists():
        filepath = category_path / f"{safe_title}_{counter}.md"
        counter += 1
        
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    tags_str = " ".join([f"#{t.strip('#')}" for t in tag_list])
    
    md_content = f"""---
url: {url}
date: {date_str}
---
# {title}

**Link**: {url}
**Tags**: {tags_str}

## Content / Metadata

{content}
"""
    try:
        filepath.write_text(md_content, encoding="utf-8")
        rel_path = filepath.relative_to(vault)
        return json.dumps({"status": "ok", "saved_to": str(rel_path), "title": title})
    except Exception as e:
        return json.dumps({"status": "error", "detail": f"Failed to write file: {e}"})

def get_link_processor_tools() -> list:
    return [process_and_save_link]
