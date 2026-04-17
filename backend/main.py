"""
HomeBotAI Telegram bot entry point.

Routes all chat messages through the Deep Agent API (/api/chat/stream)
so the Telegram bot and the dashboard share a single brain.

Differences from the API/dashboard path:
- render_ui tool calls are silently skipped (no DOM to render in Telegram)
- Responses are formatted as Telegram HTML instead of Markdown
- Photos sent by the user are downloaded and forwarded as base64 image bytes
  to the Deep Agent, which attaches them to the user message as multimodal parts
- A 'typing...' indicator is refreshed every 4 seconds while the agent is working
  so long operations (video analysis, yt-dlp downloads) do not look stalled
- Context/persona instructions live in the agent system prompt, not prepended
  to each user message
"""

import asyncio
import base64
import contextlib
import json
import logging
from collections import OrderedDict
from io import BytesIO

import aiohttp
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

import config
from bootstrap import App, create_app, shutdown_app
from notifier import _md_to_telegram_html
from reactor import Reactor

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("homebot")

app_ctx: App | None = None
reactor: Reactor | None = None

# The Deep Agent URL is the internal Docker service name when running in Docker.
# Falls back to localhost for local dev.
DEEP_AGENT_URL = config.DEEP_AGENT_URL
DEEP_AGENT_API_KEY = config.DEEP_AGENT_API_KEY

# Tool calls we suppress entirely in Telegram context
_TELEGRAM_SKIP_TOOLS = {"render_ui"}


def _is_allowed(user_id: int) -> bool:
    if not config.TELEGRAM_ALLOWED_USERS:
        return True
    return user_id in config.TELEGRAM_ALLOWED_USERS


async def _call_deepagent(
    thread_id: str,
    message: str,
    *,
    images: list[dict] | None = None,
) -> dict:
    """
    Call the Deep Agent SSE stream.

    Returns a tagged dict:
      - {"kind": "text", "text": "..."}
      - {"kind": "choices", "prompt": "...", "options": [...]}
      - {"kind": "error", "text": "..."}

    Skips render_ui tool calls entirely. When *images* is provided, each item
    should be ``{"mime": "image/jpeg", "b64": "<base64>"}``; the Deep Agent
    attaches them as multimodal parts to the user message.
    """
    url = f"{DEEP_AGENT_URL}/api/chat/stream"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": DEEP_AGENT_API_KEY,
    }
    payload = {"message": message, "thread_id": thread_id, "context": "telegram"}
    if images:
        payload["images"] = images

    response_text = "Sorry, I couldn't get a response from the agent."
    trace_url: str | None = None
    choices_event: dict | None = None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.error("DeepAgent returned %s: %s", resp.status, body[:300])
                    return {
                        "kind": "error",
                        "text": "Deep agent is unavailable right now. Try again shortly.",
                    }

                raw = await resp.read()
                body = raw.decode("utf-8", errors="ignore")

                for line in body.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue

                    event_type = data.get("type")
                    if event_type == "tool_call":
                        tool_name = data.get("name", "")
                        if tool_name not in _TELEGRAM_SKIP_TOOLS:
                            log.debug("Tool call: %s %s", tool_name, data.get("args", {}))
                    elif event_type == "choices":
                        choices_event = {
                            "prompt": data.get("prompt", ""),
                            "options": [str(o) for o in (data.get("options") or [])][:8],
                        }
                    elif event_type == "response":
                        response_text = data.get("content", response_text)
                    elif event_type == "error":
                        response_text = data.get("content", response_text)
                    elif event_type == "trace":
                        trace_url = data.get("url")

    except aiohttp.ClientConnectionError:
        log.error("Could not connect to Deep Agent at %s", DEEP_AGENT_URL)
        return {"kind": "error", "text": "Deep Agent is offline. Please check the service."}
    except Exception as e:
        log.exception("Unexpected error calling Deep Agent")
        return {"kind": "error", "text": f"Unexpected error: {e}"}

    if trace_url:
        log.info("LangSmith trace: %s", trace_url)

    if choices_event and choices_event["options"]:
        return {"kind": "choices", **choices_event}
    return {"kind": "text", "text": response_text}


@contextlib.asynccontextmanager
async def _keep_typing(bot, chat_id: int):
    """Keep Telegram's 'typing...' indicator alive for the duration of a call.

    Telegram clears the chat action after ~5 seconds, so we refresh every 4s.
    """
    stop = asyncio.Event()

    async def _loop():
        try:
            while not stop.is_set():
                try:
                    await bot.send_chat_action(chat_id=chat_id, action="typing")
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), timeout=4.0)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def _download_photo_b64(update: Update) -> tuple[str | None, str]:
    """Download the highest-resolution PhotoSize from Telegram and base64-encode it.

    Returns (base64_string, mime_type). On failure returns (None, "image/jpeg").
    """
    try:
        photos = update.message.photo
        if not photos:
            return None, "image/jpeg"
        file = await photos[-1].get_file()
        buf = BytesIO()
        await file.download_to_memory(buf)
        data = buf.getvalue()
        if not data:
            return None, "image/jpeg"
        # Telegram photos are always JPEG unless sent as a document.
        return base64.b64encode(data).decode("ascii"), "image/jpeg"
    except Exception:
        log.exception("Failed to download Telegram photo")
        return None, "image/jpeg"



# Keeps the option list for the N most recent choice messages so we can
# resolve a callback-query's short `ch:<index>` payload back to the full label.
# Keys are (chat_id, message_id). Capped to keep memory bounded.
_CHOICE_CACHE: "OrderedDict[tuple[int, int], list[str]]" = OrderedDict()
_CHOICE_CACHE_MAX = 256


def _remember_choices(chat_id: int, message_id: int, options: list[str]) -> None:
    _CHOICE_CACHE[(chat_id, message_id)] = options
    _CHOICE_CACHE.move_to_end((chat_id, message_id))
    while len(_CHOICE_CACHE) > _CHOICE_CACHE_MAX:
        _CHOICE_CACHE.popitem(last=False)


def _resolve_choice(chat_id: int, message_id: int, index: int) -> str | None:
    opts = _CHOICE_CACHE.get((chat_id, message_id))
    if not opts or index < 0 or index >= len(opts):
        return None
    return opts[index]


async def _dispatch_agent_result(
    reply_target, chat_id: int, user_msg_for_log: str, result: dict,
) -> None:
    """Render the agent's tagged response as either a message or choice buttons.

    *reply_target* is any Telegram object that exposes ``reply_text()`` --
    typically ``update.message`` or ``callback_query.message``.
    """
    kind = result.get("kind")

    if kind == "choices":
        prompt_text = result.get("prompt") or "Pick one:"
        options = result.get("options") or []
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(opt[:56], callback_data=f"ch:{i}")]
            for i, opt in enumerate(options)
        ])
        sent = await reply_target.reply_text(prompt_text, reply_markup=keyboard)
        _remember_choices(chat_id, sent.message_id, options)
        if app_ctx and app_ctx.episodic:
            await app_ctx.episodic.add(chat_id, "user", user_msg_for_log)
            await app_ctx.episodic.add(chat_id, "model", prompt_text)
        return

    response_text = result.get("text") or "(no response)"
    await _reply_formatted(reply_target, response_text)

    if app_ctx and app_ctx.episodic:
        await app_ctx.episodic.add(chat_id, "user", user_msg_for_log)
        await app_ctx.episodic.add(chat_id, "model", response_text)


async def handle_choice_callback(update: Update, context):
    """Handle taps on an offer_choices inline keyboard button."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("ch:"):
        return
    if not _is_allowed(query.from_user.id):
        await query.answer()
        return

    await query.answer()

    chat_id = query.message.chat_id
    message_id = query.message.message_id
    try:
        index = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return

    selected = _resolve_choice(chat_id, message_id, index)
    if not selected:
        await query.edit_message_text("That option has expired. Please ask again.")
        return

    # Strip the keyboard and show which option was picked, preserving the
    # original prompt for scrollback context.
    original = query.message.text or ""
    with contextlib.suppress(Exception):
        await query.edit_message_text(
            f"{original}\n\n> {selected}", reply_markup=None
        )

    thread_id = f"telegram-{chat_id}"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    async with _keep_typing(context.bot, chat_id):
        result = await _call_deepagent(thread_id=thread_id, message=selected)

    # Reuse the dispatcher so a follow-up offer_choices also works.
    await _dispatch_agent_result(query.message, chat_id, selected, result)


async def _reply_formatted(message, text: str):
    """Send a reply with markdown-to-HTML conversion, chunking, and fallback."""
    html_text = _md_to_telegram_html(text)
    chunks = (
        [html_text[i : i + 4096] for i in range(0, len(html_text), 4096)]
        if len(html_text) > 4096
        else [html_text]
    )
    for chunk in chunks:
        try:
            await message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(text[:4096], parse_mode=None)


_HELP_TEXT = (
    "HomeBotAI (Dua) is online.\n"
    "Ask me anything in plain English: control devices, check sensors, "
    "download movies, save links, search your notes.\n\n"
    "Commands:\n"
    "/help -- show this message\n"
    "/skills -- list learned skills\n"
    "/run <skill> -- run a skill on demand\n"
    "/clear -- start a fresh conversation thread\n"
)


async def cmd_start(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(_HELP_TEXT)


async def cmd_help(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(_HELP_TEXT)


async def cmd_clear(update: Update, context):
    """Start a new agent thread. Delegates to the Deep Agent's session clearer."""
    if not _is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    thread_id = f"telegram-{chat_id}"

    url = f"{DEEP_AGENT_URL}/api/chat/threads/{thread_id}"
    headers = {"X-API-Key": DEEP_AGENT_API_KEY} if DEEP_AGENT_API_KEY else {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status in (200, 204, 404):
                    await update.message.reply_text("Thread cleared. Fresh start.")
                    return
                body = await resp.text()
                log.warning("/clear returned %s: %s", resp.status, body[:200])
    except Exception:
        log.exception("Failed to clear thread")

    if app_ctx and app_ctx.episodic:
        try:
            await app_ctx.episodic.clear(chat_id)
        except Exception:
            log.exception("Failed to clear local episodic memory")

    await update.message.reply_text(
        "Thread cleared locally. The Deep Agent may still remember the last few turns."
    )


async def cmd_skills(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    skills = await app_ctx.procedural.list_skills()
    if not skills:
        await update.message.reply_text("No skills learned yet. Teach me by describing a routine!")
        return
    lines = []
    for s in skills:
        trigger_label = s.get("trigger", {}).get("type", "manual")
        lines.append(f"- {s['name']} [{trigger_label}]: {s['description']}")
    await update.message.reply_text("Learned skills:\n" + "\n".join(lines))


async def cmd_run(update: Update, context):
    """Run a skill on demand: /run <skill_name_or_id>"""
    if not _is_allowed(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /run <skill_name_or_id>\nSee /skills for available skills.")
        return

    skill_query = " ".join(context.args)
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    result_text = await reactor.fire_skill_by_name(skill_query)
    await _reply_formatted(update.message, result_text)


async def handle_message(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    user_msg = update.message.text or update.message.caption or ""
    if not user_msg.strip():
        return

    chat_id = update.effective_chat.id
    thread_id = f"telegram-{chat_id}"

    async with _keep_typing(context.bot, chat_id):
        result = await _call_deepagent(thread_id=thread_id, message=user_msg)

    await _dispatch_agent_result(update.message, chat_id, user_msg, result)


async def handle_photo(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    caption = (update.message.caption or "").strip()
    thread_id = f"telegram-{chat_id}"

    photo_b64, photo_mime = await _download_photo_b64(update)
    if not photo_b64:
        await update.message.reply_text(
            "I couldn't download that image from Telegram. Mind resending?",
            parse_mode=None,
        )
        return

    prompt_text = caption or "What is this image?"

    async with _keep_typing(context.bot, chat_id):
        result = await _call_deepagent(
            thread_id=thread_id,
            message=prompt_text,
            images=[{"mime": photo_mime, "b64": photo_b64}],
        )

    stored_user = f"[Photo] {caption}" if caption else "[Photo]"
    await _dispatch_agent_result(update.message, chat_id, stored_user, result)



async def post_init(application: Application):
    """Run after the Telegram bot application is initialized."""
    global app_ctx, reactor

    app_ctx = await create_app(connect_ha=True, build_agent=False)

    app_ctx.notifier.bot = application.bot

    # Build the ToolMap for static skill dispatch (ha_call_service etc.)
    await app_ctx.ensure_static_tools()
    reactor = Reactor(
        state_cache=app_ctx.state_cache,
        procedural=app_ctx.procedural,
        notifier=app_ctx.notifier,
    )
    reactor.set_tool_map(app_ctx.tool_map)
    await reactor.start()

    try:
        await application.bot.set_my_commands([
            BotCommand("help", "Show available commands"),
            BotCommand("skills", "List learned skills"),
            BotCommand("run", "Run a skill on demand"),
            BotCommand("clear", "Start a fresh conversation"),
        ])
    except Exception:
        log.exception("Failed to register Telegram bot commands")

    log.info("HomeBotAI fully initialized (routing chat via Deep Agent at %s)", DEEP_AGENT_URL)


async def pre_shutdown(application: Application):
    if reactor:
        await reactor.stop()
    if app_ctx:
        await shutdown_app(app_ctx)
    log.info("HomeBotAI shut down cleanly")


def main():
    tg_app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(pre_shutdown)
        .build()
    )

    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("help", cmd_help))
    tg_app.add_handler(CommandHandler("clear", cmd_clear))
    tg_app.add_handler(CommandHandler("skills", cmd_skills))
    tg_app.add_handler(CommandHandler("run", cmd_run))
    tg_app.add_handler(CallbackQueryHandler(handle_choice_callback, pattern=r"^ch:"))
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Starting HomeBotAI...")
    tg_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
