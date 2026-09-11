from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram.constants import ChatType

from app.bot.admin_access import user_has_admin_command_access


def test_missing_member_status_denies_group_command_access():
    async def get_chat_member(*, chat_id: int, user_id: int):
        return SimpleNamespace()

    user = SimpleNamespace(id=42)
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=-100123, type=ChatType.SUPERGROUP),
        effective_user=user,
        effective_message=SimpleNamespace(),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={"settings": SimpleNamespace(developer_user_ids=frozenset())}
        ),
        bot=SimpleNamespace(get_chat_member=get_chat_member),
    )

    assert asyncio.run(user_has_admin_command_access(update, context)) is False
