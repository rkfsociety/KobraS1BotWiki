from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.bot.daily_stats as daily_stats


def test_configured_daily_stats_chat_ids_prefers_allowed_chats():
    settings = SimpleNamespace(
        allowed_chat_ids=frozenset({-1002, -1001}),
        panel_admin_chat_id=-1009,
    )

    assert daily_stats.configured_daily_stats_chat_ids(settings) == (-1002, -1001)


def test_configured_daily_stats_chat_ids_falls_back_to_panel_chat():
    settings = SimpleNamespace(allowed_chat_ids=None, panel_admin_chat_id=-1009)

    assert daily_stats.configured_daily_stats_chat_ids(settings) == (-1009,)


@pytest.mark.asyncio
async def test_send_daily_stats_uses_separate_group_scopes(monkeypatch):
    monkeypatch.setattr(daily_stats, "_previous_local_day", lambda: "2026-09-13")
    requested_stats = []
    requested_topics = []

    def get_stats(_bot_data, *, chat_id, topic_id, day):
        requested_stats.append((chat_id, topic_id, day))
        return {"total_incoming": {-1001: 1, -1002: 2}[chat_id]}

    def get_topics(_bot_data, *, chat_id, topic_id, day, limit):
        requested_topics.append((chat_id, topic_id, day, limit))
        return []

    monkeypatch.setattr(daily_stats, "get_daily_stats", get_stats)
    monkeypatch.setattr(daily_stats, "get_daily_top_topics", get_topics)
    send_message = AsyncMock()
    get_chat = AsyncMock(return_value=SimpleNamespace(is_forum=True))
    application = SimpleNamespace(
        bot_data={
            "settings": SimpleNamespace(
                allowed_chat_ids=frozenset({-1002, -1001}),
                panel_admin_chat_id=-1009,
            ),
            "bot_stats": {"daily_scopes": {}},
        }
    )
    context = SimpleNamespace(
        application=application,
        bot=SimpleNamespace(send_message=send_message, get_chat=get_chat),
    )

    await daily_stats.send_daily_stats(context)

    assert requested_stats == [(-1002, None, "2026-09-13"), (-1001, None, "2026-09-13")]
    assert requested_topics == [(-1002, None, "2026-09-13", 3), (-1001, None, "2026-09-13", 3)]
    assert [call.kwargs["chat_id"] for call in send_message.await_args_list] == [-1002, -1001]
    assert all(
        call.kwargs["message_thread_id"] == daily_stats.GENERAL_TOPIC_ID
        for call in send_message.await_args_list
    )
    assert "Всего было написано 2 сообщения" in send_message.await_args_list[0].kwargs["text"]
    assert "Всего было написано 1 сообщение" in send_message.await_args_list[1].kwargs["text"]


@pytest.mark.asyncio
async def test_send_daily_stats_continues_after_one_chat_error(monkeypatch):
    send_message = AsyncMock(side_effect=[RuntimeError("chat unavailable"), None])
    get_chat = AsyncMock(return_value=SimpleNamespace(is_forum=True))
    application = SimpleNamespace(
        bot_data={
            "settings": SimpleNamespace(allowed_chat_ids=frozenset({-1001, -1002})),
            "bot_stats": {"daily_scopes": {}},
        }
    )
    context = SimpleNamespace(
        application=application,
        bot=SimpleNamespace(send_message=send_message, get_chat=get_chat),
    )

    await daily_stats.send_daily_stats(context)

    assert send_message.await_count == 2
    assert send_message.await_args_list[1].kwargs["chat_id"] == -1001


@pytest.mark.asyncio
async def test_send_daily_stats_omits_thread_for_regular_group(monkeypatch):
    monkeypatch.setattr(daily_stats, "_previous_local_day", lambda: "2026-09-13")
    send_message = AsyncMock()
    application = SimpleNamespace(
        bot_data={
            "settings": SimpleNamespace(allowed_chat_ids=frozenset({-1001})),
            "bot_stats": {"daily_scopes": {}},
        }
    )
    context = SimpleNamespace(
        application=application,
        bot=SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(is_forum=False)),
            send_message=send_message,
        ),
    )

    await daily_stats.send_daily_stats(context)

    assert "message_thread_id" not in send_message.await_args.kwargs
