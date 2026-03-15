"""
Telegram notification service.

Standalone, reusable service for sending messages to allowed Telegram users.
Can be used from Reactor, API, CLI, or standalone scripts.

The telegram library (~20s import) is loaded lazily so the API server
(which never sends Telegram messages) starts without that cost.
"""

from __future__ import annotations

import html
import logging
import re
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from telegram import Bot

log = logging.getLogger("homebot.notifier")


def _md_to_telegram_html(text: str) -> str:
    """Convert common markdown patterns to Telegram-safe HTML.

    Handles bold, italic, inline code, code blocks, and links.
    Escapes raw HTML entities so Telegram's parser doesn't choke.
    """
    text = html.escape(text)

    text = re.sub(
        r"```(?:\w*)\n?(.*?)```",
        lambda m: f"<pre>{m.group(1).strip()}</pre>",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<i>\1</i>", text)

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    return text


def _get_bot(token: str) -> Bot:
    from telegram import Bot as _Bot
    return _Bot(token=token)


def _html_parse_mode():
    from telegram.constants import ParseMode
    return ParseMode.HTML


class TelegramNotifier:
    """Sends Telegram messages to configured allowed users."""

    def __init__(
        self,
        bot: Bot | None = None,
        allowed_users: list[int] | None = None,
    ):
        self._bot = bot
        self._allowed_users = (
            allowed_users if allowed_users is not None else config.TELEGRAM_ALLOWED_USERS
        )

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            self._bot = _get_bot(config.TELEGRAM_BOT_TOKEN)
        return self._bot

    @bot.setter
    def bot(self, value: Bot):
        self._bot = value

    @property
    def allowed_users(self) -> list[int]:
        return self._allowed_users

    async def _send_one(self, uid: int, text: str, parse_mode: str | None) -> bool:
        """Send a message to one user, falling back to plain text on parse errors."""
        try:
            await self.bot.send_message(chat_id=uid, text=text, parse_mode=parse_mode)
            return True
        except Exception:
            if parse_mode:
                try:
                    await self.bot.send_message(chat_id=uid, text=text, parse_mode=None)
                    return True
                except Exception:
                    log.exception("Failed to send notification to %s (fallback)", uid)
            else:
                log.exception("Failed to send notification to %s", uid)
            return False

    async def send(
        self,
        message: str,
        *,
        chat_id: int | None = None,
        parse_mode: str | None = "auto",
    ) -> int:
        """Send a message to a specific user or all allowed users.

        parse_mode: "auto" (default) converts markdown to HTML,
                    or pass "HTML"/"MarkdownV2"/None explicitly.
        Returns the number of users successfully notified.
        """
        targets = [chat_id] if chat_id else self._allowed_users
        if not targets:
            log.warning("No notification targets configured")
            return 0

        if parse_mode == "auto":
            message = _md_to_telegram_html(message)
            parse_mode = _html_parse_mode()

        sent = 0
        for uid in targets:
            if len(message) > 4096:
                ok = True
                for i in range(0, len(message), 4096):
                    if not await self._send_one(uid, message[i : i + 4096], parse_mode):
                        ok = False
                        break
                if ok:
                    sent += 1
            else:
                if await self._send_one(uid, message, parse_mode):
                    sent += 1

        return sent
