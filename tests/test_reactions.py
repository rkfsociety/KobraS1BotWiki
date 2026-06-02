"""Реакции-эмодзи на сообщения бота: память сообщений и карточка в лог-зеркале."""
from __future__ import annotations

import logging

from app.bot.reply_logging import get_bot_message, record_bot_message
from app.bot.telegram_log_mirror import format_log_for_telegram


def _rec(msg: str) -> logging.LogRecord:
    return logging.LogRecord("root", logging.INFO, "", 0, msg, None, None)


def test_record_and_get_bot_message():
    record_bot_message(
        chat_id=-1002295062981,
        message_id=999001,
        kind="wiki",
        reply_text="ссылка",
        user_text="вопрос",
        incoming_mid=999000,
        thread=None,
    )
    info = get_bot_message(-1002295062981, 999001)
    assert info is not None
    assert info["kind"] == "wiki"
    assert get_bot_message(-1002295062981, 1) is None


def test_reaction_log_renders_card():
    line = (
        "bot_reaction emoji=\U0001f4a9 chat=-1002295062981 message_id=162691 "
        "kind=clarify_prompt user=376118338 incoming_mid=162688 thread=162688 "
        "user_text=как настроить стол reply_text=Уточните модель"
    )
    out = format_log_for_telegram(_rec(line))
    assert out is not None
    assert "негативная реакция на ответ бота" in out
    assert "\U0001f4a9" in out
    assert "376118338" in out
    # ссылки на оба сообщения: вопрос и ответ бота
    assert "/162688" in out and "/162691" in out


def test_non_reaction_line_not_treated_as_reaction():
    # Обычная строка не должна распознаваться как реакция.
    out = format_log_for_telegram(_rec("just some noise without prefix"))
    assert out is None
