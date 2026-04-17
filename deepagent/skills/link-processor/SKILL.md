---
name: link-processor
description: Process and save URLs (Instagram, YouTube, articles) to the Obsidian vault, with a pre-formatted confirmation line.
---
# Link Processor Skill

You can process links (Instagram reels, YouTube videos, web articles) and save them directly to Kanak's Obsidian vault. The tool runs metadata extraction, optional Gemini analysis, auto-categorization, and writes a Markdown note.

## Tools
- `process_and_save_link(url, category, tags)`: Fetches metadata, downloads media if applicable, runs AI summarization/analysis, auto-categorizes, and saves a Markdown note with a `## Summary` section.

## Guidelines

1. When the user pastes a URL -- on its own or with words like "save this", "add to my brain", "bookmark this" -- call `process_and_save_link` with just the URL. Let the tool auto-detect the category; do not pre-guess it unless the user tells you where to save.
2. You do NOT need to pass `category` or `tags` in normal cases -- the tool will detect both from the page/video content. Only override when the user is explicit ("save this under Recipes" / "tag it #music").
3. **Echo the `chat_reply` field verbatim.** The tool returns a pre-formatted one-liner in the `chat_reply` field of the JSON payload. Use that exact string as your reply. Do not paraphrase, summarize, or rewrite it. Do not add greetings or trailing offers.
4. The tool's `chat_reply` already encodes these states correctly:
   - Fresh save: `Saved: <title> -> Bookmarks/<Category>. <1-2 sentence summary>.`
   - Duplicate: `Already saved: <title> -> <path>.`
   - Partial save (media download failed, metadata still captured): the reply carries the warning inline (e.g. `(note: media download failed (cookies may be stale))`).
   - Error: `Failed to save <title>: <reason>.`
5. Never say "Untitled". If you see that in the response, something in the tool broke -- report it honestly rather than papering over it.
