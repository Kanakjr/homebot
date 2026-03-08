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

import config
from bootstrap import App, create_app, shutdown_app
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


async def cmd_start(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("HomeBotAI is online. Ask me anything about your home.")


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


async def handle_message(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    user_msg = update.message.text or update.message.caption or ""
    if not user_msg.strip():
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    response = await app_ctx.agent.run(chat_id=chat_id, user_message=user_msg)

    if len(response) > 4096:
        for i in range(0, len(response), 4096):
            await update.message.reply_text(response[i : i + 4096])
    else:
        await update.message.reply_text(response)


async def handle_photo(update: Update, context):
    if not _is_allowed(update.effective_user.id):
        return
    chat_id = update.effective_chat.id
    caption = update.message.caption or "What do you see in this image?"

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    response = await app_ctx.agent.run(
        chat_id=chat_id, user_message=caption, image_bytes=bytes(image_bytes),
    )

    await update.message.reply_text(response)


async def post_init(application: Application):
    """Run after the Telegram bot application is initialized."""
    global app_ctx, reactor

    app_ctx = await create_app(connect_ha=True)

    reactor = Reactor(
        state_cache=app_ctx.state_cache,
        procedural=app_ctx.procedural,
        agent=app_ctx.agent,
        bot=application.bot,
        allowed_users=config.TELEGRAM_ALLOWED_USERS,
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
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    log.info("Starting HomeBotAI...")
    tg_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
