---
name: link-processor
description: Process and save URLs (Instagram, YouTube, Articles) to the Obsidian vault.
---
# Link Processor Skill

You can process links (Instagram reels, YouTube videos, articles) and save them directly to Kanak's Obsidian vault, with Gemini-generated analysis attached.

## Tools
- `process_and_save_link(url, category, tags)`: Fetches metadata, downloads media, runs AI analysis, auto-categorizes, and saves a Markdown note.

## Guidelines

1. When the user pastes a URL -- on its own or with words like "save this", "add to my brain" -- call `process_and_save_link` with just the URL. Let the tool auto-detect the category; do not pre-guess it unless the user tells you where to save.
2. You do NOT need to pass `category` or `tags` in normal cases -- the tool will detect both from the video/image content. Only override when the user is explicit ("save this under Recipes" / "tag it #music").
3. **Handle the duplicate response gracefully.** If the tool returns `"status": "duplicate"`, tell the user the link was already saved and include the existing path. Do NOT re-process or re-save it. Example reply: `That one's already saved -- Bookmarks/DIY/3D printing adorable cat keychains.md.`
4. On a fresh save (`"status": "ok"`), confirm in one short line with the category the tool chose. Example: `Saved to Bookmarks/Tech.`
5. Do NOT tack on "let me know if you need anything else" -- the confirmation is complete on its own.
