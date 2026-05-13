"""Автоудаление пары «команда /…» + ответ бота» (кроме ответов со ссылкой на вики)."""
from __future__ import annotations

import asyncio
import logging

from telegram.constants import ChatType
from telegram.ext import ContextTypes

EPHEMERAL_SLASH_PAIR_SECONDS = 20


def _outgoing_has_wiki_link(text: str, wiki_base_url: str) -> bool:
    """Сохраняем сообщение, если в тексте есть базовый URL вики (как в исходящих HTML-ответах)."""
    base = (wiki_base_url or "").strip().rstrip("/").lower()
    if not base:
        return False
    return base in (text or "").lower()


def schedule_delete_slash_command_and_reply(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_msg,
    bot_msg,
    wiki_base_url: str,
    outgoing_text: str,
) -> None:
    """
    Через EPHEMERAL_SLASH_PAIR_SECONDS удаляет сообщение пользователя (команда) и ответ бота,
    если в ответе нет ссылки на вики (см. WIKI_BASE_URL).
    В личке с ботом пары не удаляем. В чатах из ``Settings.ephemeral_exempt_chat_ids`` — тоже не удаляем.
    """
    if _outgoing_has_wiki_link(outgoing_text, wiki_base_url):
        return
    ch = getattr(user_msg, "chat", None)
    if ch is not None and ch.type == ChatType.PRIVATE:
        return
    settings = context.application.bot_data.get("settings")
    if settings is not None and user_msg.chat_id in settings.ephemeral_exempt_chat_ids:
        return

    async def _cleanup() -> None:
        await asyncio.sleep(EPHEMERAL_SLASH_PAIR_SECONDS)
        chat_id = user_msg.chat_id
        bot = context.bot
        for mid in (user_msg.message_id, bot_msg.message_id):
            try:
                await bot.delete_message(chat_id=chat_id, message_id=mid)
            except Exception as e:
                logging.debug("ephemeral delete skip mid=%s: %s", mid, e)

    asyncio.create_task(_cleanup())
