"""
HomeBotAI Telegram bot entry point.

Routes all chat messages through the Deep Agent API (/api/chat/stream)
so the Telegram bot and the dashboard share a single brain.

Differences from the API/dashboard path:
- render_ui tool calls are silently skipped (no DOM to render in Telegram)
- Responses are formatted as Telegram HTML instead of Markdown
- Photos sent by the user are forwarded as image bytes to the agent
"""

import json
import logging

import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
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


async def _call_deepagent(thread_id: str, message: str) -> str:
    """
    Call the Deep Agent SSE stream and return the final response text.
    Skips render_ui tool calls entirely.
    """
    url = f"{DEEP_AGENT_URL}/api/chat/stream"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": DEEP_AGENT_API_KEY,
    }
    payload = {"message": message, "thread_id": thread_id}

    response_text = "Sorry, I couldn't get a response from the agent."

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    log.error("DeepAgent returned %s: %s", resp.status, body[:300])
                    return "Deep agent is unavailable right now. Try again shortly."

                # Buffer the full SSE body before parsing to avoid blank-line truncation
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
                    elif event_type == "response":
                        response_text = data.get("content", response_text)
                    elif event_type == "error":
                        response_text = data.get("content", response_text)

    except aiohttp.ClientConnectionError:
        log.error("Could not connect to Deep Agent at %s", DEEP_AGENT_URL)
        response_text = "⚠️ Deep Agent is offline. Please check the service."
    except Exception as e:
        log.exception("Unexpected error calling Deep Agent")
        response_text = f"Unexpected error: {e}"

    return response_text



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


async def cmd_start(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "HomeBotAI is online (powered by Deep Agent). Ask me anything about your home.\n\n"
        "Commands:\n"
        "/skills -- list learned skills\n"
        "/run <skill> -- run a skill on demand\n"
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
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Prepend a context hint so the deepagent knows this is Telegram
    # and should NOT use render_ui (which is only for the web dashboard)
    full_msg = (
        "[Context: This message is from the Telegram bot. "
        "Do NOT call render_ui — that tool is only for the web dashboard UI. "
        "Format your response with emojis, clear sections, and a warm engaging tone. "
        "Avoid raw markdown syntax like ** or ##; use emojis and newlines instead. "
        "Be concise and friendly, like texting with a smart home assistant.]\n\n"
        + user_msg
    )

    response_text = await _call_deepagent(thread_id=thread_id, message=full_msg)
    await _reply_formatted(update.message, response_text)


async def handle_photo(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    caption = update.message.caption or "What do you see in this image?"
    thread_id = f"telegram-{chat_id}"
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    message = (
        "[Context: This message is from the Telegram bot. Do NOT call render_ui. "
        "Format your response with emojis and a warm, conversational tone. "
        "Be concise and direct.]\n\n"
        f"[User sent a photo with caption: {caption}]"
    )
    response_text = await _call_deepagent(thread_id=thread_id, message=message)
    await _reply_formatted(update.message, response_text)



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
    tg_app.add_handler(CommandHandler("skills", cmd_skills))
    tg_app.add_handler(CommandHandler("run", cmd_run))
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Starting HomeBotAI...")
    tg_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
