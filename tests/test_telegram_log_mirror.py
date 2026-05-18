"""Зеркало лога в Telegram: полный текст входящих."""
from __future__ import annotations

import logging

from app.bot.telegram_log_mirror import LOG_MIRROR_TEXT_MAX, format_log_for_telegram


def test_seen_incoming_not_truncated_at_120():
    long_tail = "смазку для подшипников и ещё " + ("x" * 200)
    msg = (
        "seen chat=-1001 user=42 has_reply=true reply_mid=1 reply_from=99 "
        f"text=ты еще обалдеешь {long_tail}"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "смазку" in out
    assert "xxxx" in out


def test_skip_low_score_shows_query():
    q = "как смазать механизм " + ("y" * 100)
    msg = f"skip chat=-1001 reason=low_score score=59 min=72 url=https://wiki.example/x query={q}"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Текст запроса:" in out
    assert "как смазать" in out


def test_log_mirror_text_max_reasonable():
    assert LOG_MIRROR_TEXT_MAX >= 500
