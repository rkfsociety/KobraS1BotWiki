"""Может ли бот отвечать в чате/теме и входит ли контекст в ALLOWED_*."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from telegram import Chat
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from app.config import Settings

_CACHE_KEY = "reply_access_cache"
_DEFAULT_CACHE_TTL = 300.0


def chat_topic_in_allowed_lists(
    *,
    allowed_chat_ids: frozenset[int] | None,
    allowed_topic_ids: frozenset[int] | None,
    chat_id: int,
    topic_id: int | None,
) -> bool:
    """
    True — чат/тема в ALLOWED_CHAT_IDS / ALLOWED_TOPIC_IDS (или списки не заданы).

    Только чаты: сообщение в перечисленном chat_id (любая тема).
    Только темы: topic_id в списке (в любом чате).
    Оба списка: chat_id в ALLOWED_CHAT_IDS и тема подходит под ALLOWED_TOPIC_IDS.
    0 в ALLOWED_TOPIC_IDS — только General (topic_id is None).
    """
    if allowed_chat_ids is None and allowed_topic_ids is None:
        return True

    if allowed_chat_ids is not None and allowed_topic_ids is None:
        return chat_id in allowed_chat_ids

    allow_general_only = allowed_topic_ids is not None and 0 in allowed_topic_ids
    if allowed_chat_ids is None and allowed_topic_ids is not None:
        if allow_general_only:
            return topic_id is None
        return topic_id is not None and topic_id in allowed_topic_ids

    is_chat_allowed = chat_id in allowed_chat_ids
    if allow_general_only:
        is_topic_allowed = topic_id is None
    else:
        is_topic_allowed = topic_id is not None and topic_id in allowed_topic_ids
    return is_chat_allowed and is_topic_allowed


def _member_can_send_messages(member) -> bool:
    status = member.status
    if status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
        return False
    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "can_send_messages", False))
    if status == ChatMemberStatus.ADMINISTRATOR:
        return bool(getattr(member, "can_send_messages", True))
    return status in (ChatMemberStatus.OWNER, ChatMemberStatus.MEMBER)


def _member_can_send_in_forum_topic(member, *, topic_id: int | None, is_forum: bool) -> bool:
    if not is_forum or topic_id is None:
        return True
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        return bool(getattr(member, "can_send_messages_in_topics", True))
    if member.status == ChatMemberStatus.OWNER:
        return True
    # Обычный участник: достаточно can_send_messages на уровне чата.
    return _member_can_send_messages(member)


async def _closed_forum_topic_blocks_bot(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    topic_id: int,
    member,
) -> bool:
    """True — тема закрыта и бот не может в неё писать."""
    try:
        topic = await context.bot.get_forum_topic(chat_id, topic_id)
    except Exception as e:
        logging.debug("get_forum_topic chat=%s topic=%s: %s", chat_id, topic_id, e)
        return False
    if not getattr(topic, "is_closed", False):
        return False
    if member.status == ChatMemberStatus.OWNER:
        return False
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        return not bool(getattr(member, "can_manage_topics", False))
    return True


def _cache_get(context: ContextTypes.DEFAULT_TYPE, chat_id: int, topic_id: int | None) -> bool | None:
    store = context.application.bot_data.get(_CACHE_KEY)
    if not store:
        return None
    entry = store.get((chat_id, topic_id))
    if not entry:
        return None
    ok, expires = entry
    if time.monotonic() >= expires:
        store.pop((chat_id, topic_id), None)
        return None
    return ok


def _cache_put(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    topic_id: int | None,
    ok: bool,
    ttl: float,
) -> None:
    store = context.application.bot_data.setdefault(_CACHE_KEY, {})
    store[(chat_id, topic_id)] = (ok, time.monotonic() + ttl)


def invalidate_reply_access_cache(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    topic_id: int | None = None,
) -> None:
    store = context.application.bot_data.get(_CACHE_KEY)
    if not store:
        return
    store.pop((chat_id, topic_id), None)
    if topic_id is not None:
        store.pop((chat_id, None), None)


async def bot_can_reply_in_context(
    context: ContextTypes.DEFAULT_TYPE,
    chat: Chat,
    topic_id: int | None,
    *,
    cache_ttl_seconds: float = _DEFAULT_CACHE_TTL,
) -> bool:
    """
    True — бот может отправить сообщение в этот чат (и тему форума, если задана).

    Личка: всегда True. Канал: админ/владелец с правом постить.
    """
    if chat.type == ChatType.PRIVATE:
        return True

    if chat.type == ChatType.CHANNEL:
        cached = _cache_get(context, chat.id, topic_id)
        if cached is not None:
            return cached
        bot_id = context.application.bot_data.get("bot_id")
        if not bot_id:
            return True
        try:
            member = await context.bot.get_chat_member(chat.id, bot_id)
        except Exception as e:
            logging.warning("get_chat_member (bot) channel chat=%s: %s", chat.id, e)
            _cache_put(context, chat.id, topic_id, False, cache_ttl_seconds)
            return False
        ok = member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
        if ok and member.status == ChatMemberStatus.ADMINISTRATOR:
            ok = bool(getattr(member, "can_post_messages", True))
        _cache_put(context, chat.id, topic_id, ok, cache_ttl_seconds)
        return ok

    cached = _cache_get(context, chat.id, topic_id)
    if cached is not None:
        return cached

    bot_id = context.application.bot_data.get("bot_id")
    if not bot_id:
        return True

    try:
        member = await context.bot.get_chat_member(chat.id, bot_id)
    except Exception as e:
        logging.warning("get_chat_member (bot) failed chat=%s: %s", chat.id, e)
        _cache_put(context, chat.id, topic_id, False, cache_ttl_seconds)
        return False

    ok = _member_can_send_messages(member)
    if ok:
        is_forum = bool(getattr(chat, "is_forum", False))
        ok = _member_can_send_in_forum_topic(member, topic_id=topic_id, is_forum=is_forum)
    if ok and topic_id is not None and getattr(chat, "is_forum", False):
        if await _closed_forum_topic_blocks_bot(context, chat.id, topic_id, member):
            ok = False

    _cache_put(context, chat.id, topic_id, ok, cache_ttl_seconds)
    return ok


async def should_process_incoming_wiki_message(
    context: ContextTypes.DEFAULT_TYPE,
    settings: Settings,
    chat: Chat,
    chat_id: int,
    topic_id: int | None,
) -> tuple[bool, str | None]:
    """
    Можно ли обрабатывать входящее текстовое сообщение (вики/clarify).

    Возвращает (True, None) или (False, reason) — reason для LOG_DECISIONS.
    """
    if not chat_topic_in_allowed_lists(
        allowed_chat_ids=settings.allowed_chat_ids,
        allowed_topic_ids=settings.allowed_topic_ids,
        chat_id=chat_id,
        topic_id=topic_id,
    ):
        return False, "not_in_allowed_lists"

    if not settings.require_can_reply:
        return True, None

    ttl = float(settings.reply_access_cache_seconds)
    if await bot_can_reply_in_context(context, chat, topic_id, cache_ttl_seconds=ttl):
        return True, None
    return False, "cannot_reply_in_chat"
