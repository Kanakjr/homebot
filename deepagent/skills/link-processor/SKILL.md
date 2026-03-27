---
name: link-processor
description: Process and save URLs (Instagram, YouTube, Articles) to the Obsidian vault.
---
# Link Processor Skill

You can process links (like Instagram reels, YouTube videos, or articles) provided by the user and save them directly to their Obsidian vault.

## Tools
- `process_and_save_link(url, category, tags)`: Fetches metadata for a URL and saves a formatted Markdown note into a specific category folder in Obsidian.

## Guidelines
1. When the user pastes an Instagram, YouTube, or web link and asks to "save this" or "add this to my brain/notes", use the `process_and_save_link` tool.
2. Determine a relevant `category` based on the content or the user's instructions (e.g., "Recipes", "Tech", "Memes", "Bookmarks"). If unsure, default to "Bookmarks".
3. Provide relevant `tags` based on context (e.g., `["instagram", "cooking"]`).
4. Wait for the tool to return the success message and relative file path, then confirm to the user that it was saved in their vault.
