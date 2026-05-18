"""Структурированные логи решений бота (для зеркала в Telegram)."""
from __future__ import annotations

import logging
from typing import Any

from telegram import Message

# Синхронно с telegram_log_mirror.LOG_MIRROR_TEXT_MAX
LOG_MIRROR_TEXT_MAX = 1500


def telegram_message_link(
    chat_id: int,
    message_id: int,
    *,
    thread_id: int | None = None,
) -> str | None:
    """Ссылка на сообщение в супергруппе/канале (t.me/c/...). Личка — None."""
    if chat_id >= 0:
        return None
    s = str(chat_id)
    if s.startswith("-100"):
        internal = s[4:]
    elif s.startswith("-"):
        internal = str(-chat_id - 10**12)
    else:
        return None
    if not internal or internal == "0":
        return None
    if thread_id:
        return f"https://t.me/c/{internal}/{thread_id}/{message_id}"
    return f"https://t.me/c/{internal}/{message_id}"


def _msg_ids(msg: Message | None) -> tuple[int | None, int | None]:
    if msg is None:
        return None, None
    thread = getattr(msg, "message_thread_id", None)
    return msg.message_id, thread if thread else None


def log_seen_message(
    *,
    chat_id: int,
    user_id: int | str,
    msg: Message,
    has_reply: bool,
    reply_mid: int | None,
    reply_from: int | None,
    text: str,
) -> None:
    mid, thread = _msg_ids(msg)
    logging.info(
        "seen chat=%s user=%s has_reply=%s reply_mid=%s reply_from=%s mid=%s thread=%s text=%s",
        chat_id,
        user_id,
        str(has_reply).lower(),
        reply_mid,
        reply_from,
        mid,
        thread if thread else "None",
        text[:LOG_MIRROR_TEXT_MAX],
    )


def log_skip(
    chat_id: int,
    reason: str,
    *,
    msg: Message | None = None,
    **fields: Any,
) -> None:
    parts: list[str] = [f"skip chat={chat_id}", f"reason={reason}"]
    mid, thread = _msg_ids(msg)
    if mid is not None:
        parts.append(f"mid={mid}")
        if thread:
            parts.append(f"thread={thread}")
    for key, val in fields.items():
        if val is None:
            continue
        parts.append(f"{key}={val}")
    logging.info(" ".join(parts))
