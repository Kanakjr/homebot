"""
HomeBotAI Telegram bot entry point.
Uses bootstrap.py for shared initialization.
"""

import logging

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


def _is_allowed(user_id: int) -> bool:
    if not config.TELEGRAM_ALLOWED_USERS:
        return True
    return user_id in config.TELEGRAM_ALLOWED_USERS


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
            await message.reply_text(chunk if chunk == text else text, parse_mode=None)


async def cmd_start(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "HomeBotAI is online. Ask me anything about your home.\n\n"
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
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    result = await app_ctx.agent.run(chat_id=chat_id, user_message=user_msg)

    for img_path in result.images:
        try:
            with open(img_path, "rb") as f:
                await update.message.reply_photo(photo=f)
        except Exception:
            log.warning("Failed to send snapshot photo: %s", img_path)

    await _reply_formatted(update.message, result.text)


async def handle_photo(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    caption = update.message.caption or "What do you see in this image?"

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    result = await app_ctx.agent.run(
        chat_id=chat_id, user_message=caption, image_bytes=bytes(image_bytes),
    )

    for img_path in result.images:
        try:
            with open(img_path, "rb") as f:
                await update.message.reply_photo(photo=f)
        except Exception:
            log.warning("Failed to send snapshot photo: %s", img_path)

    await _reply_formatted(update.message, result.text)


async def post_init(application: Application):
    """Run after the Telegram bot application is initialized."""
    global app_ctx, reactor

    app_ctx = await create_app(connect_ha=True)

    app_ctx.notifier.bot = application.bot

    reactor = Reactor(
        state_cache=app_ctx.state_cache,
        procedural=app_ctx.procedural,
        agent=app_ctx.agent,
        notifier=app_ctx.notifier,
    )
    reactor.set_tool_map(app_ctx.tool_map)
    await reactor.start()

    log.info("HomeBotAI fully initialized (LangChain + LangSmith tracing)")


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
