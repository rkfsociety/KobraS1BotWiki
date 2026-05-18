"""Зеркало лога в Telegram: полный текст входящих."""
from __future__ import annotations
import logging
from app.bot.telegram_log_mirror import LOG_MIRROR_TEXT_MAX, format_log_for_telegram
def test_seen_incoming_not_truncated_at_120():
    long_tail = "смазку для подшипников и ещё " + ("x" * 200)
    msg = (
        "seen chat=-10012295062981 user=42 has_reply=true reply_mid=1 reply_from=99 mid=999 thread=None "
        f"text=ты еще обалдеешь {long_tail}"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "смазку" in out
    assert "xxxx" in out
def test_skip_low_score_shows_query_without_mid():
    q = "как смазать механизм " + ("y" * 100)
    msg = f"skip chat=-1001 reason=low_score score=59 min=72 url=https://wiki.example/x query={q}"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Текст запроса:" in out
    assert "как смазать" in out

def test_skip_low_score_omits_query_when_mid():
    q = "как смазать механизм " + ("y" * 100)
    msg = f"skip chat=-1001 reason=low_score mid=99 score=59 min=72 url=https://wiki.example/x query={q}"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Текст запроса:" not in out
    assert "как смазать" not in out
def test_log_mirror_text_max_reasonable():
    assert LOG_MIRROR_TEXT_MAX >= 500

from app.bot.decision_log import telegram_message_link


def test_telegram_message_link_supergroup():
    url = telegram_message_link(-1002295062981, 42)
    assert url == "https://t.me/c/2295062981/42"


def test_telegram_message_link_with_thread():
    url = telegram_message_link(-1002295062981, 99, thread_id=7)
    assert url == "https://t.me/c/2295062981/7/99"


def test_seen_log_includes_message_link():
    msg = (
        "seen chat=-1002295062981 user=42 has_reply=false reply_mid=None reply_from=None "
        "mid=12345 thread=None text=привет"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "https://t.me/c/2295062981/12345" in out
    assert "Перейти к сообщению" in out


def test_skip_log_includes_message_link():
    msg = "skip chat=-1002295062981 reason=low_score mid=12345 score=59 min=72"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "https://t.me/c/2295062981/12345" in out
