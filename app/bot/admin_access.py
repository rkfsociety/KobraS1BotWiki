"""Кто может пользоваться служебными командами бота (не вопросами в чат)."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes


def user_id_is_developer(user_id: int | None, settings) -> bool:
    """True если user_id в списке разработчиков (дефолт + DEVELOPER_USER_IDS)."""
    if user_id is None:
        return False
    return user_id in settings.developer_user_ids


async def user_has_admin_command_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """
    True — пользователь может вызывать /id, /admincheck, /wiki, /ping, /status, /error, /fix, /qaadd, /qalist, /qadel, /update.

    Разработчики (developer_user_ids) — в любых чатах, как админ служебных команд.
    В личке с ботом доступ открыт (владелец бота тестирует в DM).
    В группе/супергруппе — только создатель или администратор чата по данным Telegram.
    """
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    settings = context.application.bot_data.get("settings")
    if settings is not None and user_id_is_developer(user.id, settings):
        return True
    if chat.type == ChatType.PRIVATE:
        return True
    if chat.type == ChatType.CHANNEL:
        # В канале постить могут только админы. Пост «от имени канала» — без from_user.
        msg = update.effective_message
        if msg is not None and getattr(msg, "sender_chat", None) is not None:
            return True
        if user is None:
            return False
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
        except Exception as e:
            logging.warning("get_chat_member failed chat=%s user=%s: %s", chat.id, user.id, e)
            return False
        return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
    except Exception as e:
        logging.warning("get_chat_member failed chat=%s user=%s: %s", chat.id, user.id, e)
        return False
    return member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


async def user_exempt_from_wiki_reply_spam_limits(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """
    Не применять к ответу бота антиспам по чату (COOLDOWN_SECONDS, лимит в минуту, DUPLICATE_WINDOW).

    Совпадает с правами «служебных» команд: разработчики, админы группы, личка.
    """
    return await user_has_admin_command_access(update, context)
