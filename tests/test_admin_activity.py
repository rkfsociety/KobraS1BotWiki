"""Статистика модераторских действий админов."""
from __future__ import annotations

from app.bot.admin_activity import (
    get_admin_activity_summary,
    get_recent_admin_actions,
    load_admin_activity,
    record_admin_action,
)
from app.bot.handlers._admin_activity import classify_chat_member_update


def test_record_and_summarize_admin_actions():
    bd: dict = {}
    record_admin_action(
        bd,
        action="ban",
        admin_id=111,
        admin_username="mod1",
        target_id=222,
        target_label="@user2",
        chat_id=-100,
    )
    record_admin_action(
        bd,
        action="kick",
        admin_id=111,
        admin_username="mod1",
        target_id=333,
        chat_id=-100,
    )
    summary = get_admin_activity_summary(bd)
    assert len(summary) == 1
    assert summary[0]["total"] == 2
    assert summary[0]["counts"]["ban"] == 1
    assert summary[0]["counts"]["kick"] == 1
    recent = get_recent_admin_actions(bd)
    assert len(recent) == 2
    assert recent[0]["action"] == "kick"


def test_load_admin_activity_from_disk(tmp_path, monkeypatch):
    import app.bot.admin_activity as aa

    p = tmp_path / "admin_activity.json"
    p.write_text(
        '{"admins":{"111":{"user_id":111,"label":"@mod","counts":{"ban":3}}},'
        '"totals":{"ban":3},"recent":[],"last_updated":1}',
        encoding="utf-8",
    )
    monkeypatch.setattr(aa, "_activity_path", lambda: p)
    bd: dict = {}
    load_admin_activity(bd)
    summary = get_admin_activity_summary(bd)
    assert summary[0]["counts"]["ban"] == 3


def test_classify_ban_and_voluntary_leave():
    from types import SimpleNamespace
    from telegram.constants import ChatMemberStatus

    actor = SimpleNamespace(id=1, is_bot=False)
    target = SimpleNamespace(id=2)
    old_m = SimpleNamespace(status=ChatMemberStatus.MEMBER, user=target)
    new_banned = SimpleNamespace(status=ChatMemberStatus.BANNED, user=target)
    upd_ban = SimpleNamespace(old_chat_member=old_m, new_chat_member=new_banned, from_user=actor)
    assert classify_chat_member_update(upd_ban) == "ban"

    target_self = SimpleNamespace(id=5)
    actor_self = SimpleNamespace(id=5, is_bot=False)
    old_leave = SimpleNamespace(status=ChatMemberStatus.MEMBER, user=target_self)
    new_leave = SimpleNamespace(status=ChatMemberStatus.LEFT, user=target_self)
    upd_leave = SimpleNamespace(
        old_chat_member=old_leave,
        new_chat_member=new_leave,
        from_user=actor_self,
    )
    assert classify_chat_member_update(upd_leave) is None

    actor_mod = SimpleNamespace(id=9, is_bot=False)
    upd_kick = SimpleNamespace(
        old_chat_member=old_leave,
        new_chat_member=new_leave,
        from_user=actor_mod,
    )
    assert classify_chat_member_update(upd_kick) == "kick"
