"""Проверка прав пользователя Mini App в единственной группе бота."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

from telegram.constants import ChatMemberStatus

log = logging.getLogger(__name__)


async def _get_group_member_status(application: Any, user_id: int) -> str | None:
    """Возвращает статус участника из настроенной группы или ``None`` при ошибке."""
    bot_data = getattr(application, "bot_data", None) or {}
    settings = bot_data.get("settings")
    chat_id = getattr(settings, "panel_admin_chat_id", None)
    bot = getattr(application, "bot", None)
    if not chat_id or bot is None or not user_id:
        return None

    for attempt in range(2):
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            break
        except Exception as exc:
            if attempt == 0:
                await asyncio.sleep(0.25)
                continue
            log.warning(
                "Не удалось проверить статус Mini App пользователя %s в чате %s: %s",
                user_id,
                chat_id,
                exc,
            )
            return None

    return member.status


async def is_group_member(application: Any, user_id: int) -> bool:
    """Возвращает True для любого участника, которому доступен Mini App."""
    status = await _get_group_member_status(application, user_id)
    return status in {
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    }


async def is_group_admin(application: Any, user_id: int) -> bool:
    """Возвращает True только для creator/administrator настроенной группы."""
    status = await _get_group_member_status(application, user_id)

    return status in {
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
    }
