"""Unit tests for the deepagent link_processor tool.

These tests are offline and do not hit the network, Gemini, or yt-dlp. The
fetcher, summarizer, and media helpers are monkey-patched. Run with:

    pytest tests/deepagent/test_link_processor.py

The goal is to lock in the two behaviours that make the bookmark feature
reliable:

1. The title extraction chain always produces a non-"Untitled" title, with
   the right ``extraction_method`` attribution.
2. The ``chat_reply`` is always present, carries warnings, and is the single
   string the agent echoes to the user.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_DEEPAGENT_DIR = Path(__file__).resolve().parent.parent.parent / "deepagent"
if str(_DEEPAGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEEPAGENT_DIR))


@pytest.fixture
def isolated_vault(tmp_path, monkeypatch):
    """Point OBSIDIAN_VAULT_PATH at a tmp dir for the duration of the test."""
    import config

    monkeypatch.setattr(config, "OBSIDIAN_VAULT_PATH", str(tmp_path))
    return tmp_path


@pytest.fixture
def lp(isolated_vault):
    """Import link_processor after the vault is redirected."""
    from tools import link_processor

    return link_processor


# --- URL helpers ------------------------------------------------------------


def test_humanize_slug_prefers_last_meaningful_segment(lp):
    assert lp._humanize_slug("https://example.com/posts/how-redis-streams-work") == "How redis streams work"
    assert lp._humanize_slug("https://example.com/2024/01/how_cool_things_work") == "How cool things work"
    assert lp._humanize_slug("https://example.com/article.html") == "Article"
    assert lp._humanize_slug("https://example.com/") == "example.com"
    assert lp._humanize_slug("https://example.com/123/456/") == "example.com"


def test_canonical_url_strips_tracking_params(lp):
    a = "https://example.com/post?utm_source=twitter&id=42"
    b = "https://example.com/post?id=42&fbclid=abc"
    assert lp._canonical_url(a) == lp._canonical_url(b)


def test_canonical_url_strips_trailing_slash_and_fragment(lp):
    a = "https://example.com/post/"
    b = "https://example.com/post#section"
    assert lp._canonical_url(a) == lp._canonical_url(b)


def test_is_media_url(lp):
    assert lp._is_media_url("https://www.youtube.com/watch?v=abc")
    assert lp._is_media_url("https://youtu.be/abc")
    assert lp._is_media_url("https://www.instagram.com/reel/xyz/")
    assert not lp._is_media_url("https://example.com/article")


# --- Title extraction chain ------------------------------------------------


def test_extract_og_title_wins(lp):
    html = """
    <html><head>
      <title>Example</title>
      <meta property="og:title" content="How Redis Streams Work">
      <meta property="og:description" content="A deep dive into log structures.">
      <meta property="og:image" content="https://example.com/cover.jpg">
    </head><body><h1>irrelevant</h1></body></html>
    """
    meta = lp._extract_article_metadata(html, "https://example.com/x")
    assert meta["title"] == "How Redis Streams Work"
    assert meta["extraction_method"] == "og_title"
    assert meta["description"] == "A deep dive into log structures."
    assert meta["image"] == "https://example.com/cover.jpg"


def test_extract_twitter_title_when_no_og(lp):
    html = """
    <html><head>
      <title>Fallback</title>
      <meta name="twitter:title" content="Twitter Card Title">
    </head><body></body></html>
    """
    meta = lp._extract_article_metadata(html, "https://example.com/x")
    assert meta["title"] == "Twitter Card Title"
    assert meta["extraction_method"] == "twitter_title"


def test_extract_jsonld_headline(lp):
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Article",
       "headline":"The JSON-LD Headline","description":"ld desc"}
      </script>
    </head><body></body></html>
    """
    meta = lp._extract_article_metadata(html, "https://example.com/x")
    assert meta["title"] == "The JSON-LD Headline"
    assert meta["extraction_method"] == "json_ld"
    # description should fall back to JSON-LD when meta tags are missing
    assert meta["description"] == "ld desc"


def test_extract_jsonld_graph_nested(lp):
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph":[{"@type":"WebPage","name":"Nested Page Name"}]}
      </script>
    </head><body></body></html>
    """
    meta = lp._extract_article_metadata(html, "https://example.com/x")
    assert meta["title"] == "Nested Page Name"
    assert meta["extraction_method"] == "json_ld"


def test_extract_title_tag_fallback(lp):
    html = "<html><head><title>Plain Title &amp; More</title></head><body></body></html>"
    meta = lp._extract_article_metadata(html, "https://example.com/x")
    assert meta["title"] == "Plain Title & More"
    assert meta["extraction_method"] == "title_tag"


def test_extract_h1_fallback(lp):
    html = "<html><head></head><body><h1>The Only H1</h1></body></html>"
    meta = lp._extract_article_metadata(html, "https://example.com/x")
    assert meta["title"] == "The Only H1"
    assert meta["extraction_method"] == "h1"


def test_extract_url_slug_last_resort(lp):
    html = "<html><head></head><body></body></html>"
    meta = lp._extract_article_metadata(html, "https://example.com/posts/how-redis-streams-work")
    assert meta["title"] == "How redis streams work"
    assert meta["extraction_method"] == "url_slug"


def test_extract_never_returns_untitled_on_empty_html(lp):
    meta = lp._extract_article_metadata("", "https://example.com/something/cool-post")
    assert meta["title"] == "Cool post"
    assert meta["extraction_method"] == "url_slug"


def test_extract_article_body_uses_trafilatura(lp):
    html = """
    <html><head><title>x</title></head><body>
      <nav>nav nav nav</nav>
      <article>
        <h1>Main Heading</h1>
        <p>This is the first substantive paragraph of the article. It should be
        extracted while nav is dropped.</p>
        <p>A second paragraph to give trafilatura enough signal to pick the
        article region.</p>
      </article>
      <footer>footer junk</footer>
    </body></html>
    """
    body = lp._extract_article_body(html, "https://example.com/x")
    assert body, "trafilatura should extract the article"
    assert "first substantive paragraph" in body
    assert "footer junk" not in body


# --- Chat reply formatting --------------------------------------------------


def test_chat_reply_ok_with_summary(lp):
    reply = lp._format_chat_reply({
        "status": "ok",
        "title": "How Redis Streams Work",
        "category": "Tech",
        "summary": "A deep dive into the append-only log.",
        "saved_to": "Bookmarks/Tech/how-redis-streams-work.md",
        "warnings": [],
    })
    assert reply == "Saved: How Redis Streams Work -> Bookmarks/Tech. A deep dive into the append-only log."


def test_chat_reply_ok_without_summary(lp):
    reply = lp._format_chat_reply({
        "status": "ok",
        "title": "Some Page",
        "category": "Bookmarks",
        "summary": "",
        "warnings": [],
    })
    assert reply == "Saved: Some Page -> Bookmarks/Bookmarks."


def test_chat_reply_with_warning(lp):
    reply = lp._format_chat_reply({
        "status": "ok",
        "title": "Reel xyz",
        "category": "Comedy",
        "summary": "Funny skit.",
        "warnings": ["media download failed (cookies may be stale)"],
    })
    assert "media download failed" in reply
    assert reply.startswith("Saved: Reel xyz -> Bookmarks/Comedy.")


def test_chat_reply_duplicate(lp):
    reply = lp._format_chat_reply({
        "status": "duplicate",
        "title": "cat keychains",
        "saved_to": "Bookmarks/DIY/cat-keychains.md",
    })
    assert reply == "Already saved: cat keychains -> Bookmarks/DIY/cat-keychains.md."


def test_chat_reply_error(lp):
    reply = lp._format_chat_reply({
        "status": "error",
        "title": "some link",
        "detail": "disk full",
    })
    assert reply == "Failed to save some link: disk full."


# --- End-to-end orchestration (mocked network + LLM) -----------------------


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_process_article_happy_path(lp, isolated_vault, monkeypatch):
    fake_html = """
    <html><head>
      <meta property="og:title" content="Redis Streams Explained">
      <meta property="og:description" content="Log-structured streams.">
      <meta property="og:site_name" content="example.com">
    </head><body>
      <article><p>Redis streams are an append-only log data type.</p></article>
    </body></html>
    """
    monkeypatch.setattr(
        lp, "_fetch_html",
        lambda url, timeout=15: (fake_html, url, 200, None),
    )
    monkeypatch.setattr(
        lp, "_summarize_article",
        lambda title_hint, desc_hint, body, url: {
            "title": "Redis Streams Explained",
            "category": "Tech",
            "tags": ["redis", "streams"],
            "summary": "A deep dive into Redis's append-only log type.",
        },
    )

    raw = _run(lp.process_and_save_link("https://example.com/redis-streams"))
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["title"] == "Redis Streams Explained"
    assert payload["category"] == "Tech"
    assert payload["extraction_method"] == "og_title"
    assert payload["summary"] == "A deep dive into Redis's append-only log type."
    assert payload["chat_reply"].startswith(
        "Saved: Redis Streams Explained -> Bookmarks/Tech."
    )
    assert "A deep dive into Redis's append-only log type." in payload["chat_reply"]

    saved_path = isolated_vault / payload["saved_to"]
    assert saved_path.exists()
    note = saved_path.read_text()
    assert "## Summary" in note
    assert "A deep dive into Redis's append-only log type." in note
    assert "extraction_method: og_title" in note


def test_process_article_fetch_failure_still_saves_with_slug(lp, isolated_vault, monkeypatch):
    monkeypatch.setattr(
        lp, "_fetch_html",
        lambda url, timeout=15: ("", url, 403, "HTTP 403 Forbidden"),
    )
    monkeypatch.setattr(
        lp, "_summarize_article",
        lambda *a, **k: {"title": "", "category": "", "tags": [], "summary": ""},
    )

    raw = _run(lp.process_and_save_link("https://paywalled.example.com/posts/the-great-article"))
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    # Never "Untitled" -- slug fallback kicks in.
    assert payload["title"] == "The great article"
    assert payload["extraction_method"] == "url_slug"
    assert any("fetch failed" in w for w in payload["warnings"])
    assert "(note: fetch failed" in payload["chat_reply"]


def test_process_duplicate_short_circuits(lp, isolated_vault, monkeypatch):
    bookmarks = isolated_vault / "Bookmarks" / "Tech"
    bookmarks.mkdir(parents=True)
    existing = bookmarks / "Existing Note.md"
    existing.write_text("---\nurl: https://example.com/post\n---\n# Existing\n")

    fetches = []

    def _fake_fetch(url, timeout=15):
        fetches.append(url)
        return ("<html></html>", url, 200, None)

    monkeypatch.setattr(lp, "_fetch_html", _fake_fetch)
    monkeypatch.setattr(
        lp, "_summarize_article",
        lambda *a, **k: {"title": "", "category": "", "tags": [], "summary": ""},
    )

    raw = _run(lp.process_and_save_link("https://example.com/post?utm_source=twitter"))
    payload = json.loads(raw)

    assert payload["status"] == "duplicate"
    assert payload["chat_reply"].startswith("Already saved: Existing Note -> ")
    assert fetches == [], "duplicate detection should short-circuit before any network call"


def test_process_media_with_ytdlp_failure_falls_back_to_html(lp, isolated_vault, monkeypatch):
    """When yt-dlp can't get metadata at all, we still fetch the page's og:title."""

    def _fake_ytdlp_meta(url):
        return (lp._empty_meta(), "cookies expired")

    fake_html = """
    <html><head>
      <meta property="og:title" content="My Instagram Reel">
      <meta property="og:description" content="a fun video">
    </head></html>
    """

    monkeypatch.setattr(lp, "_fetch_metadata", _fake_ytdlp_meta)
    monkeypatch.setattr(lp, "_download_video", lambda url, out_dir: None)
    monkeypatch.setattr(lp, "_extract_instagram_image_urls", lambda url, fallback_thumbnail="": [])
    monkeypatch.setattr(
        lp, "_fetch_html",
        lambda url, timeout=15: (fake_html, url, 200, None),
    )

    raw = _run(lp.process_and_save_link("https://www.instagram.com/reel/xyz/"))
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["title"] == "My Instagram Reel"
    assert payload["extraction_method"] == "og_title"
    assert any("yt-dlp failed" in w for w in payload["warnings"])
    assert any("couldn't download the video" in w for w in payload["warnings"])
    assert "My Instagram Reel" in payload["chat_reply"]


def test_process_instagram_image_carousel_summarizes_caption(lp, isolated_vault, monkeypatch):
    """Instagram photo carousels yield metadata + description even without video.

    We should summarize the caption with Gemini, produce a clean title +
    category, save a note, and NOT complain about "cookies may be stale"
    since there's no video to download in the first place.
    """
    caption = (
        "Ex Machina (2014)\n\nDirected by Alex Garland, Ex Machina is a "
        "science fiction psychological thriller that follows a young "
        "programmer invited to evaluate an advanced artificial intelligence. "
        "Follow @filmterminal for more cinema and TV highlights."
    )

    def _fake_ytdlp_meta(url):
        meta = lp._empty_meta()
        meta.update({
            "title": "Post by filmterminal",
            "uploader": "Film Terminal",
            "description": caption,
            "n_entries": 4,
            "is_playlist": True,
            "is_image_only": True,
        })
        return (meta, None)

    download_attempts: list[str] = []

    def _fail_if_called(*_a, **_kw):
        download_attempts.append("download_video")
        return None

    monkeypatch.setattr(lp, "_fetch_metadata", _fake_ytdlp_meta)
    # _download_video must NOT be called for image-only posts -- it only emits
    # noise ("No video formats found!") and wrong warnings.
    monkeypatch.setattr(lp, "_download_video", _fail_if_called)
    monkeypatch.setattr(lp, "_extract_instagram_image_urls", lambda url, fallback_thumbnail="": [])
    monkeypatch.setattr(
        lp, "_summarize_article",
        lambda title_hint, desc_hint, body, url: {
            "title": "Ex Machina (2014) Film Analysis",
            "category": "Art",
            "tags": ["exmachina", "scifi", "filmreview"],
            "summary": "A concise review of Alex Garland's Ex Machina.",
        },
    )

    raw = _run(lp.process_and_save_link("https://www.instagram.com/p/DXDyjyWF5FT/"))
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["title"] == "Ex Machina (2014) Film Analysis - Film Terminal"
    assert payload["category"] == "Art"
    assert payload["extraction_method"] == "yt_dlp_caption"
    assert payload["warnings"] == [], (
        "image-only carousels shouldn't emit download/cookie warnings"
    )
    assert "Alex Garland" in payload["summary"]
    assert download_attempts == [], "_download_video must not run on is_image_only meta"

    expected_prefix = "Saved: Ex Machina (2014) Film Analysis - Film Terminal -> Bookmarks/Art."
    assert payload["chat_reply"].startswith(expected_prefix)
    assert "A concise review" in payload["chat_reply"]

    saved_path = isolated_vault / payload["saved_to"]
    assert saved_path.exists()
    note = saved_path.read_text()
    assert "## Summary" in note
    assert "Film Terminal" in note
    assert "Alex Garland" in note  # caption preserved in body


def test_process_instagram_image_carousel_empty_caption_falls_back_to_html(lp, isolated_vault, monkeypatch):
    """If yt-dlp reports image-only but with no caption, HTML scrape is last resort."""

    def _fake_ytdlp_meta(url):
        meta = lp._empty_meta()
        meta.update({
            "title": "",
            "uploader": "",
            "description": "",
            "is_playlist": True,
            "is_image_only": True,
        })
        return (meta, None)

    fake_html = """
    <html><head>
      <title>Instagram</title>
    </head></html>
    """

    monkeypatch.setattr(lp, "_fetch_metadata", _fake_ytdlp_meta)
    monkeypatch.setattr(lp, "_download_video", lambda url, out_dir: None)
    monkeypatch.setattr(lp, "_extract_instagram_image_urls", lambda url, fallback_thumbnail="": [])
    monkeypatch.setattr(lp, "_fetch_html", lambda url, timeout=15: (fake_html, url, 200, None))

    raw = _run(lp.process_and_save_link("https://www.instagram.com/p/AAAAAAAAAA/"))
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    # Last-resort fallback chain still gives us a usable title (the <title> tag
    # or URL slug), never "Untitled".
    assert payload["title"] and payload["title"].lower() != "untitled"


def test_process_respects_user_category_override(lp, isolated_vault, monkeypatch):
    monkeypatch.setattr(
        lp, "_fetch_html",
        lambda url, timeout=15: (
            "<html><head><title>Any</title></head></html>", url, 200, None,
        ),
    )
    monkeypatch.setattr(
        lp, "_summarize_article",
        lambda *a, **k: {"title": "Any", "category": "Tech", "tags": [], "summary": "x"},
    )

    raw = _run(lp.process_and_save_link("https://example.com/foo", category="Recipes"))
    payload = json.loads(raw)

    assert payload["category"] == "Recipes", "user override should beat Gemini's guess"
    assert "Bookmarks/Recipes" in payload["chat_reply"]
