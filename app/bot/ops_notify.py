"""Уведомления в служебный Telegram-чат (ошибки, перезапуски, запуск)."""
from __future__ import annotations

import logging

from telegram.ext import Application


def _truncate(s: str, *, max_len: int = 4000) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


async def notify_ops(application: Application, body: str) -> None:
    """Отправить текст в ``Settings.ops_notify_chat_id`` (если задан). Без parse_mode — меньше сбоев."""
    settings = application.bot_data.get("settings")
    if settings is None:
        return
    cid = getattr(settings, "ops_notify_chat_id", None)
    if cid is None:
        return
    text = _truncate(body)
    if not text:
        return
    try:
        await application.bot.send_message(
            chat_id=int(cid),
            text=text,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logging.warning("ops_notify: не удалось отправить в chat_id=%s: %s", cid, e)
