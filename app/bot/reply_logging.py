"""Логирование исходящих ответов бота (зеркало в Telegram — только bot_reply)."""
from __future__ import annotations

import html as html_mod
import logging
import re

from telegram import Message

from app.bot.decision_log import LOG_MIRROR_TEXT_MAX, _msg_ids, incoming_text_for_log

_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_log_field(text: str) -> str:
    """Одна строка в логе: переносы не ломают разбор полей в зеркале."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " · ").strip()


def _plain_text_for_log(text: str) -> str:
    """Текст ответа для зеркала: без HTML-тегов, с лимитом длины."""
    t = _TAG_RE.sub("", text or "")
    t = html_mod.unescape(t)
    return _normalize_log_field(t)[:LOG_MIRROR_TEXT_MAX]


def _log_bot_reply(
    kind: str,
    chat_id: int,
    user_id: int | None = None,
    *,
    user_text: str | None = None,
    reply_text: str | None = None,
    mid: int | None = None,
    thread: int | None = None,
    message_id: int | None = None,
    **extra: object,
) -> None:
    """Отметка в логе: бот отправил ответ в чат (ищется по `bot_reply`, зеркалится в Telegram)."""
    parts: list[str] = [f"bot_reply kind={kind}", f"chat={chat_id}"]
    if user_id is not None:
        parts.append(f"user={user_id}")
    if mid is not None:
        parts.append(f"mid={mid}")
    if thread is not None:
        parts.append(f"thread={thread}")
    if message_id is not None:
        parts.append(f"message_id={message_id}")
    for key, val in extra.items():
        if val is None:
            continue
        parts.append(f"{key}={val}")
    if user_text:
        parts.append(f"user_text={_normalize_log_field(user_text)}")
    if reply_text:
        parts.append(f"reply_text={_normalize_log_field(reply_text)}")
    logging.info(" ".join(parts))


def log_bot_reply_for_message(
    kind: str,
    *,
    msg: Message,
    reply_text: str,
    chat_id: int | None = None,
    user_id: int | None = None,
    sent: Message | None = None,
    **extra: object,
) -> None:
    """Лог ответа с текстом вопроса пользователя и текста ответа бота."""
    raw = (msg.text or msg.caption or "").strip()
    user_t = incoming_text_for_log(msg, raw) if raw else ""
    mid, thread = _msg_ids(msg)
    _log_bot_reply(
        kind,
        chat_id if chat_id is not None else msg.chat_id,
        user_id if user_id is not None else (msg.from_user.id if msg.from_user else None),
        user_text=user_t or None,
        reply_text=_plain_text_for_log(reply_text) or None,
        mid=mid,
        thread=thread,
        message_id=sent.message_id if sent else None,
        **extra,
    )
