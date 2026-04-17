"""Link processing tools -- fetch, extract, summarize, and save links to the Obsidian vault.

This module handles two URL families:

* Media URLs (YouTube/Instagram/X/TikTok): metadata via yt-dlp, optional video
  download + Gemini vision analysis. Falls back to HTML metadata if yt-dlp fails.
* Article URLs (everything else): robust HTML fetch with a browser-like UA, a
  multi-step title fallback chain (og:title -> twitter:title -> JSON-LD ->
  <title> -> <h1> -> humanized URL slug), article-body extraction via
  trafilatura, and a single-call Gemini summarization.

Every path pre-formats a ``chat_reply`` string that the agent is expected to
echo verbatim, so user-facing quality no longer depends on model whim. A
``warnings`` list carries non-fatal issues (stale cookies, failed downloads)
so failures never appear silently as an "Untitled" save.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import config

log = logging.getLogger("deepagent.tools.link_processor")

MEDIA_DOMAINS = {"youtube.com", "youtu.be", "instagram.com", "twitter.com", "x.com", "tiktok.com"}

# Query strings we strip when checking for duplicates -- these change per share
# but do not change the underlying content.
_TRACKING_PARAMS = {
    "igsh", "igshid", "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "fbclid", "gclid", "si", "feature",
    "xmt", "slof", "s", "t",
}

CATEGORIES = (
    "Culinary", "Tech", "Coffee", "Fitness", "Travel", "Music", "Comedy",
    "Education", "Finance", "Science", "Gaming", "Fashion", "Lifestyle",
    "News", "DIY", "Art", "Other",
)

# Browser-like headers. Some sites (Medium, Substack, Cloudflare-fronted) 403
# on stdlib's default "Python-urllib/3.x" agent.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Retry UA used once when the first request 403/429s. Presenting as a known
# crawler sometimes unblocks paywalls and rate limiters.
_RETRY_HEADERS = {
    **_BROWSER_HEADERS,
    "User-Agent": (
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    ),
}

_GEMINI_MODEL = "models/gemini-2.5-flash"

# --- Vault / URL utilities --------------------------------------------------


def _get_vault_path() -> Path:
    vault = Path(config.OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        vault.mkdir(parents=True, exist_ok=True)
    return vault


def _canonical_url(url: str) -> str:
    """Strip tracking params and trailing slash so dup-checks match shares of the same post."""
    from urllib.parse import urlencode, urlparse as _urlparse, parse_qsl, urlunparse

    try:
        parsed = _urlparse(url.strip())
        kept = [
            (k, v) for (k, v) in parse_qsl(parsed.query, keep_blank_values=False)
            if k not in _TRACKING_PARAMS
        ]
        path = parsed.path.rstrip("/")
        cleaned = parsed._replace(query=urlencode(kept), fragment="", path=path)
        return urlunparse(cleaned).lower()
    except Exception:
        return url.strip().rstrip("/").lower()


def _find_existing_link(url: str, vault: Path) -> Path | None:
    """Return the first Bookmarks note whose frontmatter URL matches, else None."""
    target = _canonical_url(url)
    bookmarks = vault / "Bookmarks"
    if not bookmarks.exists():
        return None

    for md in bookmarks.rglob("*.md"):
        try:
            with md.open("r", encoding="utf-8") as f:
                head = f.read(600)
        except (UnicodeDecodeError, OSError):
            continue
        match = re.search(r"^url:\s*(.+)$", head, re.MULTILINE)
        if not match:
            continue
        if _canonical_url(match.group(1)) == target:
            return md
    return None


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


def _humanize_slug(url: str) -> str:
    """Last-resort title: take the final meaningful URL path segment and title-case it.

    ``https://example.com/posts/how-redis-streams-work`` -> ``How Redis Streams Work``.
    If the path has nothing useful (all numeric / empty), returns the domain.
    """
    try:
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        for seg in reversed(segments):
            cleaned = seg.rsplit(".", 1)[0]
            if cleaned and not cleaned.isdigit():
                humanized = re.sub(r"[-_]+", " ", cleaned).strip()
                if humanized:
                    return humanized[:1].upper() + humanized[1:]
        domain = parsed.netloc.lstrip("www.")
        return domain or url
    except Exception:
        return url


# --- HTTP fetching ----------------------------------------------------------


def _fetch_html(url: str, timeout: int = 15) -> tuple[str, str, int, str | None]:
    """Fetch an HTML page with browser-like headers and one retry.

    Returns ``(html, final_url, status, error)``. ``error`` is None on success.
    Content is decoded as UTF-8 with replacement on failure; callers should
    check ``error`` before relying on the returned body.
    """

    def _do(headers: dict[str, str]) -> tuple[str, str, int, str | None]:
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                # Respect charset from Content-Type if present.
                content_type = resp.headers.get("Content-Type", "")
                charset = "utf-8"
                m = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
                if m:
                    charset = m.group(1)
                try:
                    html = body.decode(charset, errors="replace")
                except LookupError:
                    html = body.decode("utf-8", errors="replace")
                return html, resp.geturl(), resp.status, None
        except urllib.error.HTTPError as e:
            return "", url, e.code, f"HTTP {e.code} {e.reason}"
        except urllib.error.URLError as e:
            return "", url, 0, f"URL error: {e.reason}"
        except Exception as e:
            return "", url, 0, f"fetch failed: {e}"

    html, final_url, status, err = _do(_BROWSER_HEADERS)
    if err and status in (401, 403, 429):
        # Retry once with crawler-like UA; some sites unblock bots but not scripts.
        log.info("Retrying %s with crawler UA after %s", url, err)
        html, final_url, status, err = _do(_RETRY_HEADERS)
    return html, final_url, status, err


# --- HTML metadata extraction ----------------------------------------------


def _bs_parse(html: str):
    """Parse HTML with BeautifulSoup, preferring lxml when available."""
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _first_text(*candidates: Any) -> str:
    """Return the first candidate that's a non-empty, cleaned string."""
    for c in candidates:
        if not c:
            continue
        text = unescape(str(c)).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            return text
    return ""


def _extract_article_metadata(html: str, url: str) -> dict:
    """Extract a title and related metadata from HTML.

    Tries the following title sources in order and records which one worked:

    1. og:title
    2. twitter:title
    3. JSON-LD ``headline`` or ``name``
    4. ``<title>``
    5. First non-empty ``<h1>``
    6. Humanized URL slug (never returns "Untitled")

    Returns keys: ``title``, ``extraction_method``, ``description``,
    ``site_name``, ``author``, ``published``, ``image``.
    """
    result: dict[str, str] = {
        "title": "",
        "extraction_method": "",
        "description": "",
        "site_name": "",
        "author": "",
        "published": "",
        "image": "",
    }

    if not html:
        result["title"] = _humanize_slug(url)
        result["extraction_method"] = "url_slug"
        return result

    soup = _bs_parse(html)

    def _meta(attr: str, value: str) -> str:
        tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            return _first_text(tag["content"])
        return ""

    # Common descriptive fields (same source regardless of title winner).
    result["description"] = _first_text(
        _meta("property", "og:description"),
        _meta("name", "twitter:description"),
        _meta("name", "description"),
    )
    result["site_name"] = _meta("property", "og:site_name")
    result["author"] = _first_text(
        _meta("name", "author"),
        _meta("property", "article:author"),
    )
    result["published"] = _first_text(
        _meta("property", "article:published_time"),
        _meta("name", "date"),
        _meta("name", "pubdate"),
    )
    result["image"] = _first_text(
        _meta("property", "og:image"),
        _meta("name", "twitter:image"),
    )

    # Title fallback chain.
    og_title = _meta("property", "og:title")
    if og_title:
        result["title"] = og_title
        result["extraction_method"] = "og_title"
        return result

    twitter_title = _meta("name", "twitter:title")
    if twitter_title:
        result["title"] = twitter_title
        result["extraction_method"] = "twitter_title"
        return result

    jsonld_title = _extract_jsonld_title(soup)
    if jsonld_title:
        result["title"] = jsonld_title
        result["extraction_method"] = "json_ld"
        # JSON-LD often has a description too.
        if not result["description"]:
            jsonld_desc = _extract_jsonld_description(soup)
            if jsonld_desc:
                result["description"] = jsonld_desc
        return result

    if soup.title and soup.title.string:
        title_tag = _first_text(soup.title.string)
        if title_tag:
            result["title"] = title_tag
            result["extraction_method"] = "title_tag"
            return result

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        result["title"] = _first_text(h1.get_text(" ", strip=True))
        result["extraction_method"] = "h1"
        return result

    result["title"] = _humanize_slug(url)
    result["extraction_method"] = "url_slug"
    return result


def _extract_jsonld_title(soup) -> str:
    """Pull ``headline`` or ``name`` from any JSON-LD block in the page."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            # Some schemas nest under @graph.
            graph = obj.get("@graph")
            if isinstance(graph, list):
                candidates.extend([n for n in graph if isinstance(n, dict)])
            for key in ("headline", "name"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return _first_text(val)
    return ""


def _extract_jsonld_description(soup) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            val = obj.get("description")
            if isinstance(val, str) and val.strip():
                return _first_text(val)
    return ""


# --- Article body extraction -----------------------------------------------


def _extract_article_body(html: str, url: str, max_chars: int = 8000) -> str:
    """Return clean plaintext article body via trafilatura, capped for LLM input."""
    if not html:
        return ""
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
    except Exception as e:
        log.warning("trafilatura extraction failed for %s: %s", url, e)
        return ""

    if not extracted:
        return ""
    text = extracted.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "..."
    return text


# --- Gemini summarization ---------------------------------------------------


def _gemini_client():
    """Return a configured Gemini client or None if key missing."""
    try:
        import google.genai as genai
    except Exception as e:
        log.warning("google.genai not importable: %s", e)
        return None
    api_key = getattr(config, "GOOGLE_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        log.warning("Failed to init Gemini client: %s", e)
        return None


def _strip_fences(raw: str) -> str:
    """Strip ```json fences a model occasionally adds despite instructions."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)


def _summarize_article(
    title_hint: str,
    description_hint: str,
    body: str,
    url: str,
) -> dict:
    """Ask Gemini for a cleaned title, category, tags, and a 1-2 sentence summary.

    Falls back to the passed-in hints when Gemini is unavailable, so the tool
    still produces a useful save offline.
    """
    fallback = {
        "title": (title_hint or "").strip(),
        "category": "",
        "tags": [],
        "summary": (description_hint or "").strip(),
    }

    client = _gemini_client()
    if client is None:
        return fallback

    corpus = body.strip() or description_hint.strip() or title_hint.strip()
    if not corpus:
        return fallback

    prompt = (
        "You are categorizing and summarizing a saved bookmark for a personal Obsidian vault.\n\n"
        f"URL: {url}\n"
        f"Page title (may be noisy): {title_hint[:200]}\n"
        f"Page description (may be noisy): {description_hint[:400]}\n\n"
        "Article body (truncated):\n"
        f"{corpus[:6000]}\n\n"
        "Respond with ONLY this JSON object, no markdown fences, no extra text:\n"
        '{"title":"<clean, specific title, max 12 words, no site suffix>",'
        '"category":"<one of: ' + ", ".join(CATEGORIES) + '>",'
        '"tags":["<3 to 5 lowercase short tags, no hashtags, no spaces>"],'
        '"summary":"<1 to 2 sentences explaining what this page is about and why it is worth reading>"}'
    )
    try:
        resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
        )
        raw = _strip_fences(resp.text or "")
        data = json.loads(raw)
        title = (data.get("title") or "").strip()
        category = (data.get("category") or "").strip()
        summary = (data.get("summary") or "").strip()
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        return {
            "title": title or fallback["title"],
            "category": category if category in CATEGORIES else "",
            "tags": [str(t) for t in tags if t],
            "summary": summary or fallback["summary"],
        }
    except json.JSONDecodeError as e:
        log.warning("Gemini returned invalid JSON for article summary: %s", e)
        return fallback
    except Exception as e:
        log.warning("Gemini article summarization failed: %s", e)
        return fallback


# --- yt-dlp (media pipeline) ------------------------------------------------


def _yt_dlp_base_args() -> list[str]:
    args = ["yt-dlp", "--no-warnings"]
    cookies_path = getattr(config, "YTDLP_COOKIES_PATH", "") or os.environ.get("YTDLP_COOKIES_PATH", "")
    if cookies_path and Path(cookies_path).exists():
        args.extend(["--cookies", str(cookies_path)])
    return args


def _fetch_metadata(url: str) -> tuple[dict, str | None]:
    """Use yt-dlp to fetch metadata without downloading.

    Uses ``--ignore-no-formats-error`` so that Instagram photo carousels
    (which have no video formats) still return their title + description +
    uploader. ``--dump-single-json`` collapses playlists (carousels) into a
    single JSON blob with ``entries``, which is easier to parse.

    Returns ``(meta, error)``. ``meta`` carries empty strings on failure so
    the caller can detect missing fields via truthiness rather than
    sentinels. ``meta["is_image_only"]`` is True when yt-dlp found metadata
    but no video formats (i.e. image-only post) -- the orchestration uses
    this to decide whether to complain about a missing video download.
    """
    try:
        result = subprocess.run(
            _yt_dlp_base_args() + [
                "--ignore-no-formats-error",
                "--dump-single-json",
                url,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            # _type=="playlist" + no per-entry formats => image-only carousel.
            is_playlist = data.get("_type") == "playlist"
            entries = data.get("entries") or []
            entry_has_formats = any(e.get("formats") for e in entries if isinstance(e, dict))
            has_duration = bool(data.get("duration"))
            is_image_only = is_playlist and not entry_has_formats and not has_duration
            return {
                "title": data.get("title", ""),
                "uploader": data.get("uploader", ""),
                "description": data.get("description", ""),
                "duration": data.get("duration", 0),
                "view_count": data.get("view_count"),
                "like_count": data.get("like_count"),
                "comment_count": data.get("comment_count"),
                "thumbnail": data.get("thumbnail", ""),
                "ext": data.get("ext", ""),
                "entries": entries,
                "n_entries": data.get("playlist_count") or len(entries),
                "is_playlist": is_playlist,
                "is_image_only": is_image_only,
            }, None
        err = result.stderr[:300].strip() or f"returncode={result.returncode}"
        log.warning("yt-dlp metadata error: %s", err)
        return _empty_meta(), err
    except subprocess.TimeoutExpired:
        log.warning("yt-dlp metadata timed out for %s", url)
        return _empty_meta(), "yt-dlp timed out"
    except json.JSONDecodeError as e:
        log.warning("yt-dlp returned invalid JSON: %s", e)
        return _empty_meta(), f"invalid JSON from yt-dlp: {e}"
    except Exception as e:
        log.warning("yt-dlp metadata failed: %s", e)
        return _empty_meta(), str(e)


def _empty_meta() -> dict:
    return {
        "title": "",
        "uploader": "",
        "description": "",
        "duration": 0,
        "thumbnail": "",
        "ext": "",
        "entries": [],
        "n_entries": 0,
        "is_playlist": False,
        "is_image_only": False,
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
            req = urllib.request.Request(target, headers={"User-Agent": _BROWSER_HEADERS["User-Agent"]})
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
            req = urllib.request.Request(media_url, headers={"User-Agent": _BROWSER_HEADERS["User-Agent"]})
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
    """Analyze a downloaded video with Gemini vision.

    Uploads the file once then runs two calls: a compact JSON for metadata
    (title, category, tags, summary) and a free-text markdown breakdown.
    """
    try:
        import google.genai as genai

        api_key = getattr(config, "GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        if not api_key:
            return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}

        client = genai.Client(api_key=api_key)

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
                return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}
            time.sleep(3)
        else:
            log.warning("Gemini file processing timed out")
            return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}

        meta_prompt = (
            'Watch this video. Reply with ONLY this JSON object, no markdown fences, no extra text:\n'
            '{"title":"<8 words max describing what the video is about, no hashtags>",'
            '"category":"<one of: ' + ", ".join(CATEGORIES) + '>",'
            '"tags":["<tag1>","<tag2>","<tag3>"],'
            '"summary":"<1 to 2 sentences explaining what the video shows and why it is worth watching>"}'
        )
        meta_resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[file_info, meta_prompt],
        )
        raw = _strip_fences(meta_resp.text or "")
        meta = json.loads(raw)

        analysis_prompt = (
            "Analyze this video thoroughly and provide a detailed markdown report with sections:\n\n"
            "## Visual Description\n"
            "## Key Topics / Products\n"
            "## Spoken Content / Transcript Summary\n"
            "## Useful Information / Tips\n\n"
            "Be specific, detailed and actionable."
        )
        analysis_resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[file_info, analysis_prompt],
        )

        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

        return {
            "title": (meta.get("title") or "").strip(),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "summary": (meta.get("summary") or "").strip(),
            "analysis": (analysis_resp.text or "").strip(),
        }

    except json.JSONDecodeError as e:
        log.error("Gemini returned invalid JSON for video metadata: %s", e)
        return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}
    except Exception as e:
        log.error("Gemini video analysis failed: %s", e)
        return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}


def _analyze_and_categorize_images(image_paths: list[str]) -> dict:
    """Analyze one or more images with Gemini and return title/category/tags/summary/analysis."""
    if not image_paths:
        return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}

    try:
        import google.genai as genai

        api_key = getattr(config, "GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
        if not api_key:
            return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}

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
            'Analyze these Instagram post images. Reply with ONLY this JSON object, no markdown fences, no extra text:\n'
            '{"title":"<8 words max describing what this post is about, no hashtags>",'
            '"category":"<one of: ' + ", ".join(CATEGORIES) + '>",'
            '"tags":["<tag1>","<tag2>","<tag3>"],'
            '"summary":"<1 to 2 sentences describing what the post shows and why it is interesting>"}'
        )
        meta_resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[*uploaded_files, meta_prompt],
        )
        raw = _strip_fences(meta_resp.text or "")
        meta = json.loads(raw)

        analysis_prompt = (
            "Analyze these Instagram post images and provide a detailed markdown report with sections:\n\n"
            "## Visual Description\n"
            "## Key Topics / Products\n"
            "## Useful Information / Tips\n\n"
            "Be specific, detailed and actionable."
        )
        analysis_resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[*uploaded_files, analysis_prompt],
        )

        for file_name in uploaded_names:
            try:
                client.files.delete(name=file_name)
            except Exception:
                pass

        return {
            "title": (meta.get("title") or "").strip(),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "summary": (meta.get("summary") or "").strip(),
            "analysis": (analysis_resp.text or "").strip(),
        }
    except json.JSONDecodeError as e:
        log.error("Gemini returned invalid JSON for image metadata: %s", e)
        return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}
    except Exception as e:
        log.error("Gemini image analysis failed: %s", e)
        return {"title": "", "category": "Other", "tags": [], "summary": "", "analysis": ""}


# --- Chat reply formatting --------------------------------------------------


def _format_chat_reply(payload: dict) -> str:
    """Build a single short line the agent will echo verbatim to the user.

    The invariant: any warning ("couldn't download", "partial save") must be
    visible here, since the agent is instructed not to add commentary of its
    own. That way failures never show up as a confident "Saved!".
    """
    status = payload.get("status")
    title = (payload.get("title") or "").strip() or "link"
    saved_to = payload.get("saved_to") or ""
    category = (payload.get("category") or "").strip()
    summary = (payload.get("summary") or "").strip()
    warnings = payload.get("warnings") or []

    if status == "duplicate":
        path = saved_to or "Bookmarks"
        return f"Already saved: {title} -> {path}."

    if status == "error":
        detail = payload.get("detail") or "unknown error"
        return f"Failed to save {title}: {detail}."

    # ok / partial
    location = f"Bookmarks/{category}" if category else "Bookmarks"
    head = f"Saved: {title} -> {location}"

    if summary:
        head = f"{head}. {summary}"
    else:
        head = f"{head}."

    if warnings:
        head = f"{head} (note: {'; '.join(warnings)})"
    return head


# --- Orchestration ---------------------------------------------------------


async def process_and_save_link(url: str, category: str = "", tags: str = "") -> str:
    """Fetch a URL, run the appropriate pipeline, and save a note + any media.

    Returns a JSON string with at minimum:

    * ``status``: ``ok`` | ``duplicate`` | ``error``
    * ``title``, ``category``, ``tags``, ``summary``
    * ``extraction_method``: which source produced the title (``og_title``,
      ``json_ld``, ``title_tag``, ``h1``, ``url_slug``, ``yt_dlp``,
      ``gemini_video``, ``gemini_image``, ``existing``)
    * ``warnings``: list of non-fatal issues
    * ``chat_reply``: a pre-formatted one-liner the agent should echo verbatim

    Args:
        url: The Instagram reel, YouTube video, or article URL.
        category: Optional folder override (e.g. ``Recipes``). Empty -> auto.
        tags: Optional comma-separated tags, merged with AI-detected ones.
    """
    user_tags = [t.strip() for t in tags.split(",")] if tags else []
    vault = _get_vault_path()

    existing = _find_existing_link(url, vault)
    if existing is not None:
        rel = existing.relative_to(vault)
        payload = {
            "status": "duplicate",
            "saved_to": str(rel),
            "title": existing.stem,
            "category": existing.parent.name if existing.parent != vault else "",
            "extraction_method": "existing",
            "note": "already saved previously; not re-processing",
        }
        payload["chat_reply"] = _format_chat_reply(payload)
        return json.dumps(payload)

    title = ""
    summary = ""
    metadata_section = ""
    ai_analysis = ""
    ai_tags: list[str] = []
    detected_category = category or "Bookmarks"
    saved_video_rel: str | None = None
    saved_media_rel: list[str] = []
    warnings: list[str] = []
    extraction_method = ""
    og_image = ""

    if _is_media_url(url):
        meta, meta_err = _fetch_metadata(url)
        if meta_err:
            # Short, actionable. Full stderr is in logs, not in chat.
            warnings.append(f"yt-dlp failed to read the post: {meta_err[:100]}")
        title = meta.get("title", "")
        uploader = meta.get("uploader", "")
        duration_str = ""
        if meta.get("duration"):
            duration_str = f"{int(meta['duration'] // 60)}m {int(meta['duration'] % 60)}s"

        metadata_parts: list[str] = []
        if uploader:
            metadata_parts.append(f"**Uploader**: {uploader}")
        if duration_str:
            metadata_parts.append(f"**Duration**: {duration_str}")
        if meta.get("view_count"):
            metadata_parts.append(f"**Views**: {meta['view_count']:,}")
        if meta.get("like_count"):
            metadata_parts.append(f"**Likes**: {meta['like_count']:,}")
        if meta.get("n_entries") and meta.get("is_image_only"):
            metadata_parts.append(f"**Images in carousel**: {meta['n_entries']}")
        if meta.get("description"):
            metadata_parts.append(f"\n**Description**:\n{meta['description'][:1500]}")
        metadata_section = "\n".join(metadata_parts)

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths: list[str] = []
            video_path: str | None = None

            # Only attempt video download when yt-dlp reported usable formats.
            # Running _download_video on an image-only carousel produces the
            # same "No video formats found!" error and misleading warnings.
            if meta.get("is_image_only"):
                # Image carousel: try scraping the public HTML for images.
                # If Instagram requires login and scraping fails, we fall
                # through to a text-only summary based on the caption.
                image_urls = _extract_instagram_image_urls(
                    url, fallback_thumbnail=meta.get("thumbnail", "")
                )
                image_paths = _download_image_urls(image_urls, tmp_dir)
            else:
                video_path = _download_video(url, tmp_dir)
                if not video_path:
                    # Genuine download failure for something that SHOULD be a video.
                    warnings.append("couldn't download the video (check cookies/yt-dlp)")
                    if _is_instagram_post_url(url):
                        image_urls = _extract_instagram_image_urls(
                            url, fallback_thumbnail=meta.get("thumbnail", "")
                        )
                        image_paths = _download_image_urls(image_urls, tmp_dir)

            if video_path:
                log.info("Analyzing video with Gemini: %s", video_path)
                result = _analyze_and_categorize_video(video_path)
                ai_analysis = result.get("analysis", "")
                ai_tags = result.get("tags", []) or []
                summary = result.get("summary", "") or meta.get("description", "")[:220]
                extraction_method = "gemini_video"

                if not category:
                    detected_category = result.get("category") or "Other"

                ai_title = (result.get("title") or "").strip()
                if ai_title and uploader:
                    title = f"{ai_title} - {uploader}"
                elif ai_title:
                    title = ai_title

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
                ai_analysis = result.get("analysis", "")
                ai_tags = result.get("tags", []) or []
                summary = result.get("summary", "") or meta.get("description", "")[:220]
                extraction_method = "gemini_image"

                if not category:
                    detected_category = result.get("category") or "Other"

                ai_title = (result.get("title") or "").strip()
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

        # No video, no images -- if yt-dlp still gave us a caption we can run
        # the same Gemini text-summarization pipeline used for articles. This
        # turns image-carousel posts (which describe themselves in the caption)
        # into first-class notes with a real title + category + summary.
        if not saved_media_rel and meta.get("description"):
            log.info("Falling back to text summarization from caption (%d chars)", len(meta["description"]))
            result = _summarize_article(
                meta.get("title", ""),
                meta.get("description", "")[:500],
                meta.get("description", ""),
                url,
            )
            ai_title = (result.get("title") or "").strip()
            if ai_title and uploader:
                title = f"{ai_title} - {uploader}"
            elif ai_title:
                title = ai_title
            summary = result.get("summary", "") or meta.get("description", "")[:220]
            ai_tags = result.get("tags", []) or []
            if not category:
                detected_category = result.get("category") or "Other"
            extraction_method = extraction_method or (
                "yt_dlp_caption" if meta.get("is_image_only") else "yt_dlp_text"
            )

        # Final fallback: no yt-dlp data at all. Scrape the page HTML so media
        # links never save as "Untitled" even when yt-dlp breaks entirely.
        if not title:
            html, _final, _status, fetch_err = _fetch_html(url)
            if fetch_err:
                warnings.append(f"page fetch failed: {fetch_err[:100]}")
            else:
                article_meta = _extract_article_metadata(html, url)
                title = article_meta["title"]
                extraction_method = extraction_method or article_meta["extraction_method"]
                if not summary and article_meta.get("description"):
                    summary = article_meta["description"][:220]
                if not og_image and article_meta.get("image"):
                    og_image = article_meta["image"]
        elif not extraction_method:
            extraction_method = "yt_dlp"
    else:
        html, final_url, status, fetch_err = _fetch_html(url)
        if fetch_err:
            warnings.append(f"fetch failed: {fetch_err[:120]}")
            article_meta = {"title": _humanize_slug(url), "extraction_method": "url_slug",
                            "description": "", "site_name": "", "author": "", "published": "", "image": ""}
            body = ""
        else:
            article_meta = _extract_article_metadata(html, final_url or url)
            body = _extract_article_body(html, final_url or url)

        summary_result = _summarize_article(
            article_meta["title"],
            article_meta.get("description", ""),
            body,
            url,
        )

        # Gemini may return a cleaner title; keep page title if Gemini yields empty.
        title = summary_result["title"] or article_meta["title"]
        summary = summary_result["summary"] or article_meta.get("description", "")[:220]
        ai_tags = summary_result.get("tags", []) or []
        extraction_method = article_meta["extraction_method"]
        og_image = article_meta.get("image", "")

        if not category:
            detected_category = summary_result.get("category") or "Bookmarks"

        meta_lines: list[str] = []
        if article_meta.get("site_name"):
            meta_lines.append(f"**Site**: {article_meta['site_name']}")
        if article_meta.get("author"):
            meta_lines.append(f"**Author**: {article_meta['author']}")
        if article_meta.get("published"):
            meta_lines.append(f"**Published**: {article_meta['published']}")
        if article_meta.get("description"):
            meta_lines.append(f"\n**Description**: {article_meta['description']}")
        if body:
            snippet = body[:1500].rstrip()
            if len(body) > 1500:
                snippet += "..."
            meta_lines.append(f"\n**Excerpt**:\n\n{snippet}")
        metadata_section = "\n".join(meta_lines) or "Web article bookmarked."

    # Final safety net -- we should never save "Untitled".
    if not title:
        title = _humanize_slug(url)
        extraction_method = extraction_method or "url_slug"

    normalized_tags = [_normalize_tag(t) for t in (user_tags + ai_tags) if t]
    all_tags = list(dict.fromkeys([t for t in normalized_tags if t]))
    tags_str = " ".join([f"#{t}" for t in all_tags])

    category_path = vault / "Bookmarks" / detected_category
    category_path.mkdir(parents=True, exist_ok=True)
    safe_title = _clean_filename(title) or "Saved_Link"
    filepath = category_path / f"{safe_title}.md"
    counter = 1
    while filepath.exists():
        filepath = category_path / f"{safe_title}_{counter}.md"
        counter += 1

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary_section = f"\n## Summary\n\n{summary}\n" if summary else ""
    ai_section = f"\n## AI Analysis\n\n{ai_analysis}\n" if ai_analysis else ""
    media_embeds = "\n".join([f"![[{media_path}]]" for media_path in saved_media_rel])
    media_section = f"\n## Saved Media\n\n{media_embeds}\n" if media_embeds else ""
    cover_section = f"\n![Cover]({og_image})\n" if og_image and not saved_media_rel else ""

    md_content = f"""---
url: {url}
date: {date_str}
category: {detected_category}
tags: [{", ".join(all_tags)}]
extraction_method: {extraction_method}
---
# {title}

**Link**: {url}
**Tags**: {tags_str}
{cover_section}{summary_section}
## Content / Metadata

{metadata_section}{media_section}{ai_section}"""

    try:
        filepath.write_text(md_content, encoding="utf-8")
        rel_path = filepath.relative_to(vault)
        payload = {
            "status": "ok",
            "saved_to": str(rel_path),
            "title": title,
            "category": detected_category,
            "summary": summary,
            "tags": all_tags,
            "extraction_method": extraction_method,
            "video_saved": saved_video_rel,
            "media_saved": saved_media_rel,
            "ai_analyzed": bool(ai_analysis),
            "warnings": warnings,
        }
        payload["chat_reply"] = _format_chat_reply(payload)
        return json.dumps(payload)
    except Exception as e:
        payload = {
            "status": "error",
            "detail": f"Failed to write file: {e}",
            "title": title,
            "category": detected_category,
        }
        payload["chat_reply"] = _format_chat_reply(payload)
        return json.dumps(payload)


def get_link_processor_tools() -> list:
    return [process_and_save_link]
