"""Проверка допуска администраторов единственной группы к Mini App."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram.constants import ChatMemberStatus

from app.bot.miniapp_access import is_group_admin, is_group_member


def _application(status: str | None = None, *, error: Exception | None = None):
    async def get_chat_member(*, chat_id: int, user_id: int):
        assert chat_id == -100123
        assert user_id == 42
        if error:
            raise error
        return SimpleNamespace(status=status)

    return SimpleNamespace(
        bot=SimpleNamespace(get_chat_member=get_chat_member),
        bot_data={"settings": SimpleNamespace(panel_admin_chat_id=-100123)},
    )


def test_creator_is_group_admin():
    assert asyncio.run(is_group_admin(_application(ChatMemberStatus.OWNER), 42)) is True


def test_administrator_is_group_admin():
    assert asyncio.run(is_group_admin(_application(ChatMemberStatus.ADMINISTRATOR), 42)) is True


def test_regular_member_is_not_group_admin():
    assert asyncio.run(is_group_admin(_application(ChatMemberStatus.MEMBER), 42)) is False


def test_regular_and_restricted_members_are_group_members():
    assert asyncio.run(is_group_member(_application(ChatMemberStatus.MEMBER), 42)) is True
    assert asyncio.run(is_group_member(_application(ChatMemberStatus.RESTRICTED), 42)) is True


def test_telegram_api_error_denies_access():
    assert asyncio.run(is_group_admin(_application(error=RuntimeError("network")), 42)) is False
