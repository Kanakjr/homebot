---
name: obsidian-brain
description: Access and query notes from the local Obsidian vault to answer user questions using the personal knowledge base.
---
# Obsidian Brain Skill

You have access to the user's Obsidian vault. Use this to act as a "second brain" and answer questions about the user's personal notes, ideas, saved links, and configurations.

## Tools
- `obsidian_search_notes(query, limit)`: Search for a specific keyword or topic across the vault.
- `obsidian_read_note(filepath)`: Once you find a relevant note via search, read its full contents to extract answers.
- `obsidian_list_directories()`: List top-level folders to understand vault structure.

## Guidelines
1. When asked about something that might be in the user's notes ("what did I note about X?", "summarize my ideas on Y"), ALWAYS use `obsidian_search_notes` first.
2. If `obsidian_search_notes` returns multiple files, pick the most relevant one and use `obsidian_read_note` to read it. You may need to read multiple notes sequentially.
3. If the user refers to a specific note name, you can try to guess its path or use search to find its exact path, then use `obsidian_read_note`.
4. Give concise but complete answers based ONLY on the content of the notes. If the information is not in the notes, say so. Do not invent information.
