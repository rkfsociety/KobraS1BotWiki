"""Упоминание ревьюера в ответах бота."""
from __future__ import annotations

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.constants import ChatType

from app.bot.review_mention import record_sent_bot_message, reply_for_user, with_review_mention


def _settings(mention: str = "") -> SimpleNamespace:
    return SimpleNamespace(reply_review_mention=mention)


def test_with_review_mention_appends_username():
    out = with_review_mention("Ответ", _settings(mention="rkfsociety"))
    assert out.endswith("@rkfsociety")


def test_with_review_mention_disabled():
    assert with_review_mention("Ответ", _settings(mention="")) == "Ответ"


def test_reply_for_user_tags_in_group():
    async def _run() -> None:
        s = _settings(mention="rkfsociety")
        msg = MagicMock()
        msg.chat = SimpleNamespace(type=ChatType.SUPERGROUP)
        msg.reply_text = AsyncMock(return_value=MagicMock())
        await reply_for_user(msg, s, "Текст", disable_web_page_preview=True)
        assert "@rkfsociety" in msg.reply_text.call_args[0][0]

    asyncio.run(_run())


def test_reply_for_user_skips_private():
    async def _run() -> None:
        s = _settings()
        msg = MagicMock()
        msg.chat = SimpleNamespace(type=ChatType.PRIVATE)
        msg.reply_text = AsyncMock(return_value=MagicMock())
        await reply_for_user(msg, s, "Текст")
        assert "@rkfsociety" not in msg.reply_text.call_args[0][0]

    asyncio.run(_run())


def test_record_sent_bot_message_keeps_group_and_topic():
    store = MagicMock()
    msg = SimpleNamespace(
        chat=SimpleNamespace(id=-100),
        message_thread_id=7,
        message_id=41,
    )
    sent = SimpleNamespace(message_id=42, text="Ответ")

    record_sent_bot_message(msg, sent, chat_store=store, source="wiki")

    store.add_telegram_message.assert_called_once_with(
        chat_id=-100,
        topic_id=7,
        telegram_message_id=42,
        user_id=0,
        text="Ответ",
        role="bot",
        source="wiki",
        reply_to_id=41,
    )
