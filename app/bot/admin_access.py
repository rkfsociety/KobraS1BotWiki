"""Кто может пользоваться служебными командами бота (не вопросами в чат)."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from app.bot.constants import COOLDOWN_EXEMPT_USERS


async def user_has_admin_command_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """
    True — пользователь может вызывать /id, /wiki, /ping, /status, /error, /fix, /qaadd, /qalist, /qadel, /update.

    В личке с ботом доступ открыт (владелец бота тестирует в DM).
    В группе/супергруппе — только создатель или администратор чата по данным Telegram.
    """
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    if chat.type == ChatType.PRIVATE:
        return True
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

    Исключения: ручной allowlist user id; администратор чата (как для /wiki); личка с ботом.
    """
    user = update.effective_user
    if user and user.id in COOLDOWN_EXEMPT_USERS:
        return True
    return await user_has_admin_command_access(update, context)
