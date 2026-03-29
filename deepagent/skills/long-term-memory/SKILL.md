---
name: long-term-memory
description: Persistent user memory in markdown under Obsidian homebot-brain — preferences, facts, how the user names devices, phrase-to-entity mappings, and anything they ask you to remember. Do not offer Home Assistant automations when they only want you to remember wording.
tags: [memory, preferences, obsidian, persistent]
---

# Long-term memory (homebot-brain)

You have **durable** memory stored as Markdown under the vault subfolder **`homebot-brain`** (configured via the environment). This is separate from the ephemeral skill files and from searching the whole Obsidian vault: use these tools for **agent-maintained, cross-session** notes the user can also edit in Obsidian.

## Tools

- `memory_list_notes()`: List all `.md` files under the brain folder (recursive), paths relative to that folder.
- `memory_search_notes(query, limit)`: Keyword search **only** inside `homebot-brain` (use before reading a specific file when unsure where information lives).
- `memory_read_note(relative_path)`: Read one file; path is relative to the brain root (e.g. `preferences.md`, `topics/home.md`).
- `memory_write_note(relative_path, content, append)`: Create or replace a file. Use `append=true` to append a dated block without replacing the whole file.

## When to read

- The user’s message may depend on **earlier preferences, facts, or instructions** you or they stored.
- Before acting in a way that could **contradict** something they asked you to remember.
- When resolving **user-specific** phrasing or context (search first, then read the best match).
- If other skills imply “check what we saved” — consult memory.

## When to write

- Explicit: “remember …”, “don’t forget …”, “note that …”, “for future reference …”.
- Implicit standing rules: “always …”, “I prefer …”, “never …” when they clearly want persistence.
- Phrase ↔ device mappings: “associate … with …”, “when I say X I mean …”, “call that Y”, “bedroom light = bedside …” — **save the mapping** in `homebot-brain` (e.g. `home/device-phrases.md` or append to `home/context.md`) with the **exact Home Assistant `entity_id`** they intend.
- Corrections or facts they want retained across chats.
- Optional: summarize multi-turn outcomes into a compact note when they ask to save progress.

### Home Assistant automations vs memory

If the user only wants **you** to understand a colloquial name (so future chat commands work), **persist with `memory_write_note`** and confirm. **Do not** push Home Assistant automations, voice triggers, or YAML unless they **explicitly** ask to automate in HA. Declining an automation (“no”) means stick to memory, not insist on another automation pitch.

## Organization (inspired by common memory patterns)

Use **descriptive relative paths**; split by topic instead of one giant file when it helps:

- Examples: `preferences.md`, `facts.md`, `home/context.md`, `instructions.md`, or topical files under subfolders.
- You may loosely mirror **semantic** (facts/preferences), **episodic** (what happened), **procedural** (how to behave)—as separate files or sections—not as rigid categories.

## Guidelines

1. Prefer `memory_search_notes` when you do not know the filename; then `memory_read_note`.
2. Prefer `append=true` when adding a dated log entry; overwrite when replacing structured content.
3. Do not store secrets (passwords, tokens); remind the user if they ask to save sensitive data.
4. This skill is **general-purpose**—smart-home wording is one topic among many.
5. For device commands, **read memory before** claiming an entity does not exist: search for words from the user’s phrase (e.g. “bedroom”, “bedside”) and apply any stored mapping to the correct `entity_id`.
