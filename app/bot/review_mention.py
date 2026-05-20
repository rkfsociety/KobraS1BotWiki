"""Упоминание ревьюера в ответах бота в группах (чтобы приходило уведомление)."""
from __future__ import annotations

from telegram import Message
from telegram.constants import ChatType

from app.config import Settings


def _mention_line(settings: Settings) -> str:
    raw = (getattr(settings, "reply_review_mention", None) or "").strip()
    if not raw or raw.lower() in ("0", "off", "false", "no", "-"):
        return ""
    return raw if raw.startswith("@") else f"@{raw}"


def with_review_mention(body: str, settings: Settings) -> str:
    mention = _mention_line(settings)
    if not mention:
        return body
    if mention.lower() in (body or "").lower():
        return body
    base = (body or "").rstrip()
    return f"{base}\n\n{mention}" if base else mention


def should_tag_reviewer(msg: Message) -> bool:
    chat = msg.chat
    if not chat:
        return False
    return chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def reply_for_user(
    msg: Message,
    settings: Settings,
    text: str,
    *,
    log_kind: str | None = None,
    log_extra: dict | None = None,
    log_user_id: int | None = None,
    **kwargs,
) -> Message:
    """reply_text с @ревьюером в группах (не в личке); опционально — лог в зеркало Telegram."""
    body = text
    if should_tag_reviewer(msg):
        body = with_review_mention(text, settings)
    sent = await msg.reply_text(body, **kwargs)
    if log_kind:
        from app.bot.reply_logging import log_bot_reply_for_message

        log_bot_reply_for_message(
            log_kind,
            msg=msg,
            reply_text=body,
            sent=sent,
            user_id=log_user_id,
            **(log_extra or {}),
        )
    return sent
