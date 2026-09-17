"""Уведомления в служебный Telegram-чат (ошибки, перезапуски, запуск)."""
from __future__ import annotations

import logging

from telegram.ext import Application

from app.bot.review_mention import record_outgoing_bot_message


def _truncate(s: str, *, max_len: int = 4000) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


async def notify_ops(
    application: Application,
    body: str,
    *,
    parse_mode: str | None = None,
) -> None:
    """Отправить текст в ``Settings.ops_notify_chat_id`` (если задан)."""
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
        kwargs: dict = {"chat_id": int(cid), "text": text, "disable_web_page_preview": True}
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
        sent = await application.bot.send_message(**kwargs)
        chat_store = application.bot_data.get("chat_store")
        if chat_store is not None:
            record_outgoing_bot_message(
                chat_store,
                sent,
                chat_id=int(cid),
                text=text,
                source="ops_notify",
            )
    except Exception as e:
        logging.warning("ops_notify: не удалось отправить в chat_id=%s: %s", cid, e)
