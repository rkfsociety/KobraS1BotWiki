from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram.constants import ChatMemberStatus, ChatType

from app.bot.admin_access import (
    bot_has_moderation_right,
    user_has_admin_command_access,
    user_has_moderation_command_access,
)


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


def _moderation_update(*, chat_type=ChatType.SUPERGROUP, user_id=42):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=-100123, type=chat_type),
        effective_user=SimpleNamespace(id=user_id),
        effective_message=SimpleNamespace(),
    )


def _member_context(member):
    async def get_chat_member(chat_id, user_id):
        return member

    return SimpleNamespace(bot=SimpleNamespace(get_chat_member=get_chat_member))


def test_moderation_access_allows_group_owner_and_admin():
    for status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
        assert asyncio.run(
            user_has_moderation_command_access(
                _moderation_update(), _member_context(SimpleNamespace(status=status))
            )
        ) is True


def test_moderation_access_denies_member_and_private_chat():
    member_context = _member_context(SimpleNamespace(status=ChatMemberStatus.MEMBER))
    assert asyncio.run(user_has_moderation_command_access(_moderation_update(), member_context)) is False

    private_context = _member_context(SimpleNamespace(status=ChatMemberStatus.OWNER))
    assert asyncio.run(
        user_has_moderation_command_access(
            _moderation_update(chat_type=ChatType.PRIVATE), private_context
        )
    ) is False


def test_bot_moderation_right_requires_admin_capability():
    async def get_me():
        return SimpleNamespace(id=99)

    async def get_chat_member(chat_id, user_id):
        return SimpleNamespace(
            status=ChatMemberStatus.ADMINISTRATOR,
            can_restrict_members=True,
            can_delete_messages=False,
        )

    context = SimpleNamespace(bot=SimpleNamespace(get_me=get_me, get_chat_member=get_chat_member))
    assert asyncio.run(bot_has_moderation_right(context, -100123, "can_restrict_members")) is True
    assert asyncio.run(bot_has_moderation_right(context, -100123, "can_delete_messages")) is False
    assert asyncio.run(bot_has_moderation_right(context, -100123, "unknown_right")) is False


def test_bot_owner_has_moderation_rights():
    async def get_me():
        return SimpleNamespace(id=99)

    async def get_chat_member(chat_id, user_id):
        return SimpleNamespace(status=ChatMemberStatus.OWNER)

    context = SimpleNamespace(bot=SimpleNamespace(get_me=get_me, get_chat_member=get_chat_member))
    assert asyncio.run(bot_has_moderation_right(context, -100123, "can_restrict_members")) is True
