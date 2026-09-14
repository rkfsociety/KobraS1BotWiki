"""Проверки команд модерации без обращения к Telegram."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from telegram.constants import ChatMemberStatus, ChatType

from app.bot.handlers._cmd_moderation import (
    _parse_duration,
    cmd_ban,
    cmd_del,
    cmd_mute,
    cmd_pin,
    cmd_unban,
    cmd_unmute,
    cmd_unpin,
    cmd_warn,
)
from app.bot.moderation import add_warning, clear_warnings, get_warnings, remove_warning


def test_parse_duration_defaults_to_one_hour_and_extracts_reason():
    assert _parse_duration([]) == (3600, "")
    assert _parse_duration(["2h", "спам"]) == (7200, "спам")
    assert _parse_duration(["3d"]) == (259200, "")
    assert _parse_duration(["29s"]) is None
    assert _parse_duration(["31d"]) is None
    assert _parse_duration(["спам"]) == (3600, "спам")


def test_warning_store_add_remove_and_clear(tmp_path, monkeypatch):
    import app.bot.moderation as moderation

    monkeypatch.setattr(moderation, "_store_path", lambda: tmp_path / "moderation.json")
    data: dict = {}
    assert add_warning(data, chat_id=-100, user_id=7, admin_id=1, admin_label="@mod", reason="спам") == 1
    assert add_warning(data, chat_id=-100, user_id=7, admin_id=1, admin_label="@mod", reason="ссылка") == 2
    assert len(get_warnings(data, chat_id=-100, user_id=7)) == 2
    assert remove_warning(data, chat_id=-100, user_id=7) == 1
    assert clear_warnings(data, chat_id=-100, user_id=7) == 1
    assert get_warnings(data, chat_id=-100, user_id=7) == []
    assert (tmp_path / "moderation.json").exists()


def _update(*, command: str, target_id: int = 7):
    target = SimpleNamespace(id=target_id, username="target", first_name="Target", full_name="Target", is_bot=False)
    admin = SimpleNamespace(id=1, username="mod", first_name="Mod", full_name="Mod", is_bot=False)
    target_message = SimpleNamespace(from_user=target, message_id=10)
    message = SimpleNamespace(
        text=f"/{command}",
        caption=None,
        from_user=admin,
        reply_to_message=target_message,
        message_id=11,
        replies=[],
    )

    async def reply_text(text, **kwargs):
        message.replies.append(text)
        return SimpleNamespace(message_id=12)

    message.reply_text = reply_text
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=-100123, type=ChatType.SUPERGROUP),
        effective_user=admin,
        effective_message=message,
    )


def _context(data: dict, *, restricted: bool = True):
    async def get_chat_member(chat_id, user_id):
        if user_id in (1, 99):
            return SimpleNamespace(
                status=ChatMemberStatus.ADMINISTRATOR,
                can_restrict_members=True,
                can_delete_messages=True,
                can_pin_messages=True,
            )
        return SimpleNamespace(status=ChatMemberStatus.MEMBER)

    async def get_me():
        return SimpleNamespace(id=99)

    async def restrict_chat_member(**kwargs):
        data["restrict"] = kwargs

    async def ban_chat_member(**kwargs):
        data["ban"] = kwargs

    async def unban_chat_member(**kwargs):
        data["unban"] = kwargs

    async def delete_message(**kwargs):
        data.setdefault("deleted", []).append(kwargs)

    async def pin_chat_message(**kwargs):
        data["pin"] = kwargs

    async def unpin_chat_message(**kwargs):
        data["unpin"] = kwargs

    bot = SimpleNamespace(
        get_chat_member=get_chat_member,
        get_me=get_me,
        restrict_chat_member=restrict_chat_member,
        ban_chat_member=ban_chat_member,
        unban_chat_member=unban_chat_member,
        delete_message=delete_message,
        pin_chat_message=pin_chat_message,
        unpin_chat_message=unpin_chat_message,
    )
    return SimpleNamespace(application=SimpleNamespace(bot_data=data), bot=bot, args=[])


def test_cmd_mute_uses_reply_target_and_bot_restrict_right(monkeypatch):
    monkeypatch.setattr("app.bot.handlers._cmd_moderation._record", lambda *args: None)
    data = {"settings": SimpleNamespace()}
    update = _update(command="mute")
    context = _context(data)
    asyncio.run(cmd_mute(update, context))
    assert data["restrict"]["user_id"] == 7
    assert data["restrict"]["permissions"].can_send_messages is False
    assert data["restrict"]["until_date"] > 0
    assert update.effective_message.replies[0].startswith("Пользователь @target замьючен")


def test_cmd_warn_persists_warning_and_records_reply(monkeypatch, tmp_path):
    import app.bot.moderation as moderation

    monkeypatch.setattr(moderation, "_store_path", lambda: tmp_path / "moderation.json")
    data = {"moderation_store": {"warnings": {}, "last_updated": 0}}
    update = _update(command="warn")
    context = _context(data)
    context.args = ["спам"]
    monkeypatch.setattr("app.bot.handlers._cmd_moderation._record", lambda *args: None)
    asyncio.run(cmd_warn(update, context))
    assert len(get_warnings(data, chat_id=-100123, user_id=7)) == 1
    assert "№1" in update.effective_message.replies[0]


def test_member_commands_record_successful_actions(monkeypatch):
    actions = []
    monkeypatch.setattr(
        "app.bot.handlers._cmd_moderation._record",
        lambda _context, _update, action, _target: actions.append(action),
    )

    for command, handler in (
        ("ban", cmd_ban),
        ("unban", cmd_unban),
        ("mute", cmd_mute),
        ("unmute", cmd_unmute),
    ):
        data = {"settings": SimpleNamespace()}
        update = _update(command=command)
        context = _context(data)
        asyncio.run(handler(update, context))

    assert actions == ["ban", "unban", "restrict", "unrestrict"]


def test_message_commands_call_telegram_and_record_success(monkeypatch):
    actions = []
    monkeypatch.setattr(
        "app.bot.handlers._cmd_moderation._record_message",
        lambda _context, _update, action, _message: actions.append(action),
    )

    for command, handler in (("del", cmd_del), ("pin", cmd_pin), ("unpin", cmd_unpin)):
        data = {"settings": SimpleNamespace()}
        update = _update(command=command)
        context = _context(data)
        asyncio.run(handler(update, context))
        assert data.get("deleted") or data.get(command)

    assert actions == ["delete", "pin", "unpin"]
