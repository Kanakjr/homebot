"""Link processing tools — fetch, analyze with Gemini vision, auto-categorize, and save to Obsidian vault."""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import config

log = logging.getLogger("deepagent.tools.link_processor")

MEDIA_DOMAINS = {"youtube.com", "youtu.be", "instagram.com", "twitter.com", "x.com", "tiktok.com"}


def _get_vault_path() -> Path:
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        vault.mkdir(parents=True, exist_ok=True)
    return vault


def _clean_filename(text: str, max_len: int = 50) -> str:
    return re.sub(r"[^\w\s-]", "", text).strip()[:max_len]


def _is_media_url(url: str) -> bool:
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return any(d in domain for d in MEDIA_DOMAINS)


def _fetch_metadata(url: str) -> dict:
    """Use yt-dlp --dump-json to fetch video metadata without downloading."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-warnings", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip().split("\n")[0])
            return {
                "title": data.get("title", "Untitled"),
                "uploader": data.get("uploader", ""),
                "description": data.get("description", ""),
                "duration": data.get("duration", 0),
                "view_count": data.get("view_count"),
                "like_count": data.get("like_count"),
            }
        log.warning("yt-dlp metadata error: %s", result.stderr[:300])
    except Exception as e:
        log.warning("yt-dlp metadata failed: %s", e)
    return {"title": "Untitled", "uploader": "", "description": "", "duration": 0}


def _download_video(url: str, out_dir: str) -> str | None:
    """Download the video to a temp file, return the file path or None on failure."""
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-warnings",
                "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "--merge-output-format", "mp4",
                "-o", os.path.join(out_dir, "video.%(ext)s"),
                url,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            for f in os.listdir(out_dir):
                if f.startswith("video"):
                    return os.path.join(out_dir, f)
        log.warning("yt-dlp download error: %s", result.stderr[:300])
    except Exception as e:
        log.warning("yt-dlp download failed: %s", e)
    return None
def _analyze_and_categorize_video(video_path: str) -> dict:
    """
    Upload video ONCE to Gemini Files API, then run two lightweight inference calls
    (both reuse the cached file_info — no re-upload):
      1. Short JSON call: title, category, tags  (avoids JSON escaping issues)
      2. Free-text call : detailed markdown analysis
    Returns dict with keys: title, category, tags, analysis.
    """
    try:
        import google.genai as genai

        api_key = getattr(config, "GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        if not api_key:
            return {"title": "", "category": "Other", "tags": [], "analysis": ""}

        client = genai.Client(api_key=api_key)

        # ── Upload once ────────────────────────────────────────────────────────
        log.info("Uploading video to Gemini Files API: %s", video_path)
        with open(video_path, "rb") as f:
            uploaded = client.files.upload(
                file=f,
                config={"mime_type": "video/mp4", "display_name": "link_analysis"},
            )

        log.info("Waiting for Gemini to process video (file: %s)...", uploaded.name)
        for _ in range(30):
            file_info = client.files.get(name=uploaded.name)
            if file_info.state.name == "ACTIVE":
                break
            if file_info.state.name == "FAILED":
                log.warning("Gemini file processing failed")
                return {"title": "", "category": "Other", "tags": [], "analysis": ""}
            time.sleep(3)
        else:
            log.warning("Gemini file processing timed out")
            return {"title": "", "category": "Other", "tags": [], "analysis": ""}

        # ── Call 1: short JSON metadata (small fields only, no escaping issues) ─
        meta_prompt = (
            'Watch this video. Reply with ONLY this JSON object, no markdown fences, '
            'no extra text:\n'
            '{"title":"<8 words max describing what the video is about, no hashtags>",'
            '"category":"<one of: Culinary, Tech, Coffee, Fitness, Travel, Music, Comedy, '
            'Education, Finance, Science, Gaming, Fashion, Lifestyle, News, DIY, Art, Other>",'
            '"tags":["<tag1>","<tag2>","<tag3>"]}'
        )
        meta_resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[file_info, meta_prompt],
        )
        raw = re.sub(r"^```json\s*|\s*```$", "", meta_resp.text.strip())
        meta = json.loads(raw)

        # ── Call 2: free-text analysis (reuses the already-cached file_info) ───
        analysis_prompt = (
            "Analyze this video thoroughly and provide a detailed markdown report with sections:\n\n"
            "## Visual Description\n"
            "## Key Topics / Products\n"
            "## Spoken Content / Transcript Summary\n"
            "## Useful Information / Tips\n\n"
            "Be specific, detailed and actionable."
        )
        analysis_resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[file_info, analysis_prompt],
        )

        # Clean up uploaded file
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

        return {
            "title": meta.get("title", "").strip(),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "analysis": analysis_resp.text.strip(),
        }

    except json.JSONDecodeError as e:
        log.error("Gemini returned invalid JSON for metadata: %s", e)
        return {"analysis": "", "category": "Other", "tags": [], "title": ""}
    except Exception as e:
        log.error("Gemini video analysis failed: %s", e)
        return {"analysis": "", "category": "Other", "tags": [], "title": ""}



async def process_and_save_link(url: str, category: str = "", tags: str = "") -> str:
    """Fetch a URL, download and AI-analyze any video, auto-categorize, then save note + video to Obsidian vault.

    For video links (Instagram, YouTube, TikTok etc.), the video is:
    1. Downloaded locally
    2. Analyzed by Gemini 2.5 Flash (visual description, transcript, tips, category)
    3. Saved to the Obsidian vault under the detected category
    4. A linked Markdown note is created referencing the saved video file

    Args:
        url: The Instagram reel, YouTube video, or web article URL.
        category: Optional folder override (e.g. 'Bookmarks', 'Recipes'). If empty, Gemini auto-detects.
        tags: Optional comma-separated string of tags (e.g. 'instagram,coffee'). Merged with AI-detected tags.
    """
    user_tags = [t.strip() for t in tags.split(",")] if tags else []
    vault = _get_vault_path()

    title = "Untitled Link"
    metadata_section = ""
    ai_analysis = ""
    ai_tags: list[str] = []
    detected_category = category or "Bookmarks"
    saved_video_rel: str | None = None

    if _is_media_url(url):
        # Step 1: get metadata (fast, no download)
        meta = _fetch_metadata(url)
        title = meta["title"]
        duration_str = f"{int(meta['duration'] // 60)}m {int(meta['duration'] % 60)}s" if meta["duration"] else ""

        metadata_section = (
            f"**Uploader**: {meta['uploader']}\n"
            + (f"**Duration**: {duration_str}\n" if duration_str else "")
            + (f"**Views**: {meta['view_count']:,}\n" if meta.get("view_count") else "")
            + f"\n**Description**:\n{meta['description'][:1000]}\n"
        )

        # Step 2: download video, analyze + categorize, then save video permanently
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = _download_video(url, tmp_dir)
            if video_path:
                log.info("Analyzing video with Gemini: %s", video_path)
                result = _analyze_and_categorize_video(video_path)
                ai_analysis = result["analysis"]
                ai_tags = result["tags"]

                # Use Gemini's category unless user overrode it
                if not category:
                    detected_category = result["category"]

                # Build display title: "{AI description} - {uploader}"
                ai_title = result.get("title", "").strip()
                uploader = meta.get("uploader", "").strip()
                if ai_title and uploader:
                    title = f"{ai_title} - {uploader}"
                elif ai_title:
                    title = ai_title
                # else keep original API title as fallback

                # Save video permanently into vault/Bookmarks/Media/{category}/
                ext = Path(video_path).suffix or ".mp4"
                safe_title = _clean_filename(title, max_len=50) or "video"
                media_dir = vault / "Bookmarks" / "Media" / detected_category
                media_dir.mkdir(parents=True, exist_ok=True)
                video_dest = media_dir / f"{safe_title}{ext}"
                if video_dest.exists():
                    video_dest = media_dir / f"{safe_title}_{int(time.time())}{ext}"
                shutil.copy2(video_path, video_dest)
                saved_video_rel = str(video_dest.relative_to(vault))
                log.info("Saved video to vault: %s", saved_video_rel)
            else:
                log.warning("Video download failed, saving note with metadata only")
    else:
        # Web article fallback
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
                if match:
                    title = match.group(1).strip()
            metadata_section = "Web article bookmarked."
        except Exception as e:
            metadata_section = f"Failed to fetch webpage: {e}"

    # Merge user tags + AI tags
    all_tags = list(dict.fromkeys(user_tags + ai_tags))  # dedup, preserve order
    tags_str = " ".join([f"#{t.strip('#')}" for t in all_tags if t])

    # Build note file path — always inside Bookmarks/{category}/
    category_path = vault / "Bookmarks" / detected_category
    category_path.mkdir(parents=True, exist_ok=True)
    safe_title = _clean_filename(title) or "Saved_Link"
    filepath = category_path / f"{safe_title}.md"
    counter = 1
    while filepath.exists():
        filepath = category_path / f"{safe_title}_{counter}.md"
        counter += 1

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    ai_section = f"\n## 🤖 AI Analysis\n\n{ai_analysis}\n" if ai_analysis else ""
    video_section = (
        f"\n## 📹 Saved Video\n\n![[{saved_video_rel}]]\n"
        if saved_video_rel else ""
    )

    md_content = f"""---
url: {url}
date: {date_str}
category: {detected_category}
tags: [{", ".join(all_tags)}]
---
# {title}

**Link**: {url}
**Tags**: {tags_str}

## Content / Metadata

{metadata_section}{video_section}{ai_section}"""

    try:
        filepath.write_text(md_content, encoding="utf-8")
        rel_path = filepath.relative_to(vault)
        return json.dumps({
            "status": "ok",
            "saved_to": str(rel_path),
            "title": title,
            "category": detected_category,
            "video_saved": saved_video_rel,
            "ai_analyzed": bool(ai_analysis),
            "tags": all_tags,
        })
    except Exception as e:
        return json.dumps({"status": "error", "detail": f"Failed to write file: {e}"})


def get_link_processor_tools() -> list:
    return [process_and_save_link]
