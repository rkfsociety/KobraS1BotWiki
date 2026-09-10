"""Проверка allowlist чатов/тем (reply_access)."""
from __future__ import annotations

from types import SimpleNamespace

from app.bot.reply_access import (
    _cache_get,
    _cache_put,
    can_bot_reply_in_context,
    chat_topic_in_allowed_lists,
)


def test_collect_only_context_cannot_send_reply():
    assert not can_bot_reply_in_context(answer_context=False, bot_can_send=True)
    assert not can_bot_reply_in_context(answer_context=True, bot_can_send=False)
    assert can_bot_reply_in_context(answer_context=True, bot_can_send=True)


def test_reply_access_cache_is_bounded(monkeypatch):
    context = SimpleNamespace(application=SimpleNamespace(bot_data={}))
    monkeypatch.setattr("app.bot.reply_access._CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr("app.bot.reply_access.time.monotonic", lambda: 100.0)

    _cache_put(context, 1, None, True, 300)
    _cache_put(context, 2, None, True, 300)
    _cache_put(context, 3, None, False, 300)

    store = context.application.bot_data["reply_access_cache"]
    assert len(store) == 2
    assert _cache_get(context, 1, None) is None
    assert _cache_get(context, 2, None) is True
    assert _cache_get(context, 3, None) is False


def test_reply_access_cache_recovers_from_corrupted_entries(monkeypatch):
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={"reply_access_cache": {"broken": "value", (1, None): (True, float("nan"))}}
        )
    )
    monkeypatch.setattr("app.bot.reply_access.time.monotonic", lambda: 100.0)

    assert _cache_get(context, 1, None) is None
    _cache_put(context, 2, None, True, "broken")

    assert _cache_get(context, 2, None) is None
    assert isinstance(context.application.bot_data["reply_access_cache"], dict)


def test_no_lists_allows_everywhere():
    assert chat_topic_in_allowed_lists(
        allowed_chat_ids=None,
        allowed_topic_ids=None,
        chat_id=-1001,
        topic_id=5,
    )


def test_chat_allowlist():
    allowed = frozenset({-1001})
    assert chat_topic_in_allowed_lists(
        allowed_chat_ids=allowed,
        allowed_topic_ids=None,
        chat_id=-1001,
        topic_id=99,
    )
    assert not chat_topic_in_allowed_lists(
        allowed_chat_ids=allowed,
        allowed_topic_ids=None,
        chat_id=-1002,
        topic_id=None,
    )


def test_topic_allowlist():
    allowed_topics = frozenset({10, 20})
    assert chat_topic_in_allowed_lists(
        allowed_chat_ids=None,
        allowed_topic_ids=allowed_topics,
        chat_id=-1001,
        topic_id=10,
    )
    assert not chat_topic_in_allowed_lists(
        allowed_chat_ids=None,
        allowed_topic_ids=allowed_topics,
        chat_id=-1001,
        topic_id=None,
    )


def test_general_only_topic_zero():
    allowed_topics = frozenset({0})
    assert chat_topic_in_allowed_lists(
        allowed_chat_ids=None,
        allowed_topic_ids=allowed_topics,
        chat_id=-1001,
        topic_id=None,
    )
    assert not chat_topic_in_allowed_lists(
        allowed_chat_ids=None,
        allowed_topic_ids=allowed_topics,
        chat_id=-1001,
        topic_id=42,
    )


def test_both_lists_require_chat_and_topic():
    """Чат в ALLOWED_CHAT_IDS не открывает все темы форума — нужна и тема из ALLOWED_TOPIC_IDS."""
    chats = frozenset({-1001})
    topics = frozenset({10, 20})
    assert chat_topic_in_allowed_lists(
        allowed_chat_ids=chats,
        allowed_topic_ids=topics,
        chat_id=-1001,
        topic_id=10,
    )
    assert not chat_topic_in_allowed_lists(
        allowed_chat_ids=chats,
        allowed_topic_ids=topics,
        chat_id=-1001,
        topic_id=99,
    )
    assert not chat_topic_in_allowed_lists(
        allowed_chat_ids=chats,
        allowed_topic_ids=topics,
        chat_id=-1002,
        topic_id=10,
    )
