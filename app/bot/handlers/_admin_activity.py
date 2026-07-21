"""Обработка модераторских событий: бан, кик, мут, закреп."""
from __future__ import annotations

import logging

from telegram import ChatMemberUpdated, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

from app.bot.admin_activity import record_admin_action
from app.bot.reply_access import chat_topic_in_allowed_lists

log = logging.getLogger(__name__)


def _target_label(user) -> str | None:
    if user is None:
        return None
    if user.username:
        return f"@{user.username}"
    name = (user.first_name or "").strip()
    if name:
        return name
    return str(user.id)


def classify_chat_member_update(update: ChatMemberUpdated) -> str | None:
    """Классифицирует изменение статуса участника."""
    old_m = update.old_chat_member
    new_m = update.new_chat_member
    actor = update.from_user
    target = new_m.user
    if actor is None or target is None:
        return None

    old_s = old_m.status
    new_s = new_m.status

    if new_s == ChatMemberStatus.BANNED:
        return "ban"

    if new_s == ChatMemberStatus.LEFT:
        if actor.id == target.id:
            return None
        return "kick"

    if old_s == ChatMemberStatus.BANNED and new_s in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
        ChatMemberStatus.ADMINISTRATOR,
    ):
        return "unban"

    if new_s == ChatMemberStatus.RESTRICTED:
        old_can = getattr(old_m, "can_send_messages", True)
        new_can = getattr(new_m, "can_send_messages", True)
        if old_s == ChatMemberStatus.RESTRICTED:
            if old_can and not new_can:
                return "restrict"
            if not old_can and new_can:
                return "unrestrict"
            return None
        if not new_can:
            return "restrict"
        return None

    if new_s == ChatMemberStatus.ADMINISTRATOR and old_s != ChatMemberStatus.ADMINISTRATOR:
        return "promote"

    if old_s == ChatMemberStatus.ADMINISTRATOR and new_s != ChatMemberStatus.ADMINISTRATOR:
        return "demote"

    return None


def _allowed_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int, topic_id: int | None) -> bool:
    settings = context.application.bot_data.get("settings")
    if settings is None:
        return False
    return chat_topic_in_allowed_lists(
        allowed_chat_ids=settings.allowed_chat_ids,
        allowed_topic_ids=settings.allowed_topic_ids,
        chat_id=chat_id,
        topic_id=topic_id,
    )


async def on_chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cm = update.chat_member
    if cm is None:
        return

    chat = cm.chat
    if chat is None:
        return
    if not _allowed_chat(context, chat.id, None):
        return

    actor = cm.from_user
    target = cm.new_chat_member.user
    if actor is None or target is None:
        return
    if actor.is_bot:
        return

    action = classify_chat_member_update(cm)
    if not action:
        return

    record_admin_action(
        context.application.bot_data,
        action=action,
        admin_id=actor.id,
        admin_username=actor.username,
        admin_first_name=actor.first_name,
        target_id=target.id,
        target_label=_target_label(target),
        chat_id=chat.id,
    )
    log.info(
        "admin_activity %s admin=%s target=%s chat=%s",
        action,
        actor.id,
        target.id,
        chat.id,
    )


async def on_left_chat_member_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запасной канал: сервисное сообщение «X покинул чат» при кике."""
    msg = update.effective_message
    if msg is None or msg.left_chat_member is None or msg.from_user is None:
        return
    chat = update.effective_chat
    if chat is None:
        return
    if not _allowed_chat(context, chat.id, msg.message_thread_id):
        return

    actor = msg.from_user
    target = msg.left_chat_member
    if actor.is_bot or actor.id == target.id:
        return

    record_admin_action(
        context.application.bot_data,
        action="kick",
        admin_id=actor.id,
        admin_username=actor.username,
        admin_first_name=actor.first_name,
        target_id=target.id,
        target_label=_target_label(target),
        chat_id=chat.id,
    )


async def on_pinned_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or msg.from_user is None:
        return
    chat = update.effective_chat
    if chat is None:
        return
    if not _allowed_chat(context, chat.id, msg.message_thread_id):
        return

    actor = msg.from_user
    if actor.is_bot:
        return

    pinned = msg.pinned_message
    target_id = pinned.from_user.id if pinned and pinned.from_user else None
    target_label = _target_label(pinned.from_user) if pinned and pinned.from_user else None

    record_admin_action(
        context.application.bot_data,
        action="pin",
        admin_id=actor.id,
        admin_username=actor.username,
        admin_first_name=actor.first_name,
        target_id=target_id,
        target_label=target_label,
        chat_id=chat.id,
    )
