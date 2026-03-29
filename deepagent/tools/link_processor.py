"""Link processing tools — fetch, analyze with Gemini vision, auto-categorize, and save to Obsidian vault."""

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

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


def _normalize_tag(tag: str) -> str:
    """Normalize tags for Obsidian: no spaces, use hyphens."""
    cleaned = tag.strip().lstrip("#")
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    return cleaned.strip("-")


def _is_media_url(url: str) -> bool:
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return any(d in domain for d in MEDIA_DOMAINS)


def _is_instagram_post_url(url: str) -> bool:
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")
    return domain == "instagram.com" and "/p/" in parsed.path.lower()


def _yt_dlp_base_args() -> list[str]:
    args = ["yt-dlp", "--no-warnings"]
    cookies_path = getattr(config, "YTDLP_COOKIES_PATH", "") or os.environ.get("YTDLP_COOKIES_PATH", "")
    if cookies_path and Path(cookies_path).exists():
        args.extend(["--cookies", str(cookies_path)])
    return args


def _fetch_metadata(url: str) -> dict:
    """Use yt-dlp --dump-json to fetch video metadata without downloading."""
    try:
        result = subprocess.run(
            _yt_dlp_base_args() + ["--dump-json", url],
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
                "thumbnail": data.get("thumbnail", ""),
                "ext": data.get("ext", ""),
                "entries": data.get("entries", []),
            }
        log.warning("yt-dlp metadata error: %s", result.stderr[:300])
    except Exception as e:
        log.warning("yt-dlp metadata failed: %s", e)
    return {
        "title": "Untitled",
        "uploader": "",
        "description": "",
        "duration": 0,
        "thumbnail": "",
        "ext": "",
        "entries": [],
    }


def _download_video(url: str, out_dir: str) -> str | None:
    """Download the video to a temp file, return the file path or None on failure."""
    try:
        result = subprocess.run(
            _yt_dlp_base_args() + [
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


def _extract_instagram_image_urls(url: str, fallback_thumbnail: str = "") -> list[str]:
    """Extract image URLs from Instagram post HTML (single and carousel posts)."""
    candidates: list[str] = []
    urls_to_try = [url]
    if not url.rstrip("/").endswith("/embed"):
        urls_to_try.append(url.rstrip("/") + "/embed/")

    patterns = [
        r'<meta\s+property="og:image"\s+content="([^"]+)"',
        r'"display_url":"(https:\\/\\/[^"]+)"',
        r'"display_src":"(https:\\/\\/[^"]+)"',
        r'"thumbnail_src":"(https:\\/\\/[^"]+)"',
    ]

    for target in urls_to_try:
        try:
            req = urllib.request.Request(target, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            for pattern in patterns:
                for m in re.findall(pattern, html):
                    candidates.append(m.replace("\\/", "/"))
        except Exception as e:
            log.warning("Failed to extract Instagram image URLs from %s: %s", target, e)

    if fallback_thumbnail:
        candidates.append(fallback_thumbnail)

    deduped: list[str] = []
    seen: set[str] = set()
    for media_url in candidates:
        cleaned = media_url.strip()
        if not cleaned:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _download_image_urls(image_urls: list[str], out_dir: str, max_images: int = 10) -> list[str]:
    """Download images from direct URLs to temp files."""
    downloaded: list[str] = []
    for idx, media_url in enumerate(image_urls[:max_images], start=1):
        try:
            req = urllib.request.Request(media_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                ext = mimetypes.guess_extension(content_type) or Path(urlparse(media_url).path).suffix or ".jpg"
                if ext.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    ext = ".jpg"
                file_path = os.path.join(out_dir, f"image_{idx}{ext}")
                with open(file_path, "wb") as f:
                    f.write(resp.read())
                downloaded.append(file_path)
        except Exception as e:
            log.warning("Failed to download Instagram image %s: %s", media_url, e)
    return downloaded
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


def _analyze_and_categorize_images(image_paths: list[str]) -> dict:
    """Analyze one or more images with Gemini and return title/category/tags/analysis."""
    if not image_paths:
        return {"analysis": "", "category": "Other", "tags": [], "title": ""}

    try:
        import google.genai as genai

        api_key = getattr(config, "GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        if not api_key:
            return {"analysis": "", "category": "Other", "tags": [], "title": ""}

        client = genai.Client(api_key=api_key)
        uploaded_names: list[str] = []
        uploaded_files = []
        for image_path in image_paths[:4]:
            mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
            with open(image_path, "rb") as f:
                uploaded = client.files.upload(
                    file=f,
                    config={"mime_type": mime_type, "display_name": "link_analysis_image"},
                )
                uploaded_files.append(uploaded)
                uploaded_names.append(uploaded.name)

        meta_prompt = (
            'Analyze these Instagram post images. Reply with ONLY this JSON object, no markdown fences, '
            'no extra text:\n'
            '{"title":"<8 words max describing what this post is about, no hashtags>",'
            '"category":"<one of: Culinary, Tech, Coffee, Fitness, Travel, Music, Comedy, '
            'Education, Finance, Science, Gaming, Fashion, Lifestyle, News, DIY, Art, Other>",'
            '"tags":["<tag1>","<tag2>","<tag3>"]}'
        )
        meta_resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[*uploaded_files, meta_prompt],
        )
        raw = re.sub(r"^```json\s*|\s*```$", "", meta_resp.text.strip())
        meta = json.loads(raw)

        analysis_prompt = (
            "Analyze these Instagram post images and provide a detailed markdown report with sections:\n\n"
            "## Visual Description\n"
            "## Key Topics / Products\n"
            "## Useful Information / Tips\n\n"
            "Be specific, detailed and actionable."
        )
        analysis_resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=[*uploaded_files, analysis_prompt],
        )

        for file_name in uploaded_names:
            try:
                client.files.delete(name=file_name)
            except Exception:
                pass

        return {
            "title": meta.get("title", "").strip(),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "analysis": analysis_resp.text.strip(),
        }
    except json.JSONDecodeError as e:
        log.error("Gemini returned invalid JSON for image metadata: %s", e)
        return {"analysis": "", "category": "Other", "tags": [], "title": ""}
    except Exception as e:
        log.error("Gemini image analysis failed: %s", e)
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
    saved_media_rel: list[str] = []

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

        # Step 2: download media and analyze with Gemini
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths: list[str] = []
            video_path = _download_video(url, tmp_dir)
            if not video_path and _is_instagram_post_url(url):
                image_urls = _extract_instagram_image_urls(url, fallback_thumbnail=meta.get("thumbnail", ""))
                image_paths = _download_image_urls(image_urls, tmp_dir)

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
                saved_media_rel.append(saved_video_rel)
                log.info("Saved video to vault: %s", saved_video_rel)
            elif image_paths:
                log.info("Analyzing Instagram images with Gemini: %s files", len(image_paths))
                result = _analyze_and_categorize_images(image_paths)
                ai_analysis = result["analysis"]
                ai_tags = result["tags"]

                if not category:
                    detected_category = result["category"]

                ai_title = result.get("title", "").strip()
                uploader = meta.get("uploader", "").strip()
                if ai_title and uploader:
                    title = f"{ai_title} - {uploader}"
                elif ai_title:
                    title = ai_title

                media_dir = vault / "Bookmarks" / "Media" / detected_category
                media_dir.mkdir(parents=True, exist_ok=True)

                for image_path in image_paths:
                    ext = Path(image_path).suffix or ".jpg"
                    safe_title = _clean_filename(title, max_len=45) or "image"
                    image_dest = media_dir / f"{safe_title}{ext}"
                    if image_dest.exists():
                        image_dest = media_dir / f"{safe_title}_{int(time.time() * 1000)}{ext}"
                    shutil.copy2(image_path, image_dest)
                    saved_media_rel.append(str(image_dest.relative_to(vault)))
            else:
                log.warning("Media download failed, saving note with metadata only")
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
    normalized_tags = [_normalize_tag(t) for t in (user_tags + ai_tags) if t]
    all_tags = list(dict.fromkeys([t for t in normalized_tags if t]))  # dedup, preserve order
    tags_str = " ".join([f"#{t}" for t in all_tags])

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
    media_embeds = "\n".join([f"![[{media_path}]]" for media_path in saved_media_rel])
    media_section = f"\n## Saved Media\n\n{media_embeds}\n" if media_embeds else ""

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

{metadata_section}{media_section}{ai_section}"""

    try:
        filepath.write_text(md_content, encoding="utf-8")
        rel_path = filepath.relative_to(vault)
        return json.dumps({
            "status": "ok",
            "saved_to": str(rel_path),
            "title": title,
            "category": detected_category,
            "video_saved": saved_video_rel,
            "media_saved": saved_media_rel,
            "ai_analyzed": bool(ai_analysis),
            "tags": all_tags,
        })
    except Exception as e:
        return json.dumps({"status": "error", "detail": f"Failed to write file: {e}"})


def get_link_processor_tools() -> list:
    return [process_and_save_link]
