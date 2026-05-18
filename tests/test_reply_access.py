"""Проверка allowlist чатов/тем (reply_access)."""
from __future__ import annotations

from app.bot.reply_access import chat_topic_in_allowed_lists


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
