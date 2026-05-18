"""Упоминание ревьюера в ответах бота."""
from __future__ import annotations

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock, MagicMock

from telegram.constants import ChatType

from app.bot.review_mention import reply_for_user, with_review_mention


def _settings(mention: str = "rkfsociety") -> SimpleNamespace:
    return SimpleNamespace(reply_review_mention=mention)


def test_with_review_mention_appends_username():
    out = with_review_mention("Ответ", _settings())
    assert out.endswith("@rkfsociety")


def test_with_review_mention_disabled():
    assert with_review_mention("Ответ", _settings(mention="")) == "Ответ"


def test_reply_for_user_tags_in_group():
    async def _run() -> None:
        s = _settings()
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
