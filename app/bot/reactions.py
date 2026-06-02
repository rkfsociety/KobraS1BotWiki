"""Реакции-эмодзи на сообщения бота: ловим негатив (💩/👎) и пишем в лог-зеркало.

Telegram отдаёт реакции отдельным апдейтом ``message_reaction`` (MessageReactionUpdated),
который содержит только chat_id + message_id и того, кто реагировал — без автора целевого
сообщения. Поэтому «своё ли это сообщение» определяем по памяти отправленных ответов
(``app.bot.reply_logging.get_bot_message``).

Чтобы апдейты реакций вообще приходили в группах, бот должен быть администратором чата
(ограничение Telegram). allowed_updates уже = ALL_TYPES.
"""
from __future__ import annotations

import logging

from telegram import ReactionTypeEmoji, Update
from telegram.ext import ContextTypes

from app.bot.admin_access import user_has_admin_command_access, user_id_is_developer
from app.bot.decision_log import _normalize_log_line_text
from app.bot.reply_logging import get_bot_message


def _emoji_set(reactions) -> set[str]:
    """Из списка ReactionType достаём только обычные эмодзи."""
    out: set[str] = set()
    for r in reactions or ():
        if isinstance(r, ReactionTypeEmoji) and r.emoji:
            out.add(r.emoji)
    return out


async def _reaction_from_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Реакцию поставил админ/разработчик (или анонимный админ от имени чата)."""
    mr = update.message_reaction
    if mr is None:
        return False
    settings = context.application.bot_data.get("settings")
    if mr.user is None:
        # Анонимный админ / реакция «от имени канала или группы».
        return mr.actor_chat is not None
    if settings is not None and user_id_is_developer(mr.user.id, settings):
        return True
    return await user_has_admin_command_access(update, context)


async def on_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик апдейта message_reaction: логируем негатив на ответ бота."""
    mr = update.message_reaction
    if mr is None or mr.chat is None:
        return
    settings = context.application.bot_data.get("settings")
    if settings is None:
        return

    added = _emoji_set(mr.new_reaction) - _emoji_set(mr.old_reaction)
    negative = added & set(settings.negative_reaction_emojis)
    if not negative:
        return

    info = get_bot_message(mr.chat.id, mr.message_id)
    if info is None:
        # Реакция не на сообщение бота (или оно уже вытеснено из памяти) — игнорируем.
        return

    if settings.reaction_log_admin_only and not await _reaction_from_admin(update, context):
        if getattr(settings, "log_decisions", False):
            logging.info(
                "reaction_skip non_admin chat=%s message_id=%s",
                mr.chat.id,
                mr.message_id,
            )
        return

    emoji = "".join(sorted(negative))
    user_id = mr.user.id if mr.user else None
    kind = str(info.get("kind") or "?")
    user_text = _normalize_log_line_text(str(info.get("user_text") or ""))
    reply_text = _normalize_log_line_text(str(info.get("reply_text") or ""))
    incoming_mid = info.get("incoming_mid")
    thread = info.get("thread")

    parts = [
        f"bot_reaction emoji={emoji}",
        f"chat={mr.chat.id}",
        f"message_id={mr.message_id}",
        f"kind={kind}",
    ]
    if user_id is not None:
        parts.append(f"user={user_id}")
    if incoming_mid is not None:
        parts.append(f"incoming_mid={incoming_mid}")
    if thread is not None:
        parts.append(f"thread={thread}")
    if user_text:
        parts.append(f"user_text={user_text}")
    if reply_text:
        parts.append(f"reply_text={reply_text}")
    logging.info(" ".join(parts))
