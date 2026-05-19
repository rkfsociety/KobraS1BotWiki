"""Зеркало лога в Telegram: полный текст входящих."""
from __future__ import annotations
import logging
from app.bot.decision_log import incoming_text_for_log
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


def test_skip_not_triggered_suppressed_in_mirror():
    # «not_triggered» — самая частая причина: блок «Входящее» уже отдал чат+ссылку+текст,
    # отдельный блок «Решение: пропуск» лишь дублирует поля, поэтому в зеркало не уходит.
    msg = "skip chat=-1002295062981 reason=not_triggered mid=12345 user=42"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    assert format_log_for_telegram(record) is None


def test_skip_quiet_reasons_suppressed_in_mirror():
    # Группа «не для бота»: ни одна из этих причин не должна зеркалиться отдельным блоком.
    for reason in (
        "not_a_question",
        "conversational_chatter",
        "marketplace_promo",
        "slash_command",
    ):
        msg = f"skip chat=-1001 reason={reason} mid=99 user=42"
        record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
        assert format_log_for_telegram(record) is None, reason


def test_skip_low_score_still_mirrored():
    # Содержательные причины (бот пытался ответить, но не смог) остаются в зеркале.
    msg = "skip chat=-1002295062981 reason=low_score mid=12345 score=59 min=72"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Решение: пропуск" in out


def test_seen_multiline_text_in_mirror():
    msg = (
        "seen chat=-1001 user=42 has_reply=false reply_mid=None reply_from=None "
        "mid=99 thread=None text=строка один · строка два"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "строка один" in out
    assert "строка два" in out


def test_bot_reply_with_user_and_query():
    msg = (
        "bot_reply kind=wiki chat=-1001 user=42 score=80 url=https://wiki.example/x "
        "query=как смазать подшипник"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Решение: ответ в чат" in out
    assert "как смазать" in out
    assert "Пользователь:" in out


def test_startup_ready_compact_mirror():
    msg = "startup_ready bot=AnycubicWiki_bot wiki=1703 qa=1 codes=92 fix=0 pid=12345 index_done=true"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "Бот запущен" in out
    assert "@AnycubicWiki_bot" in out
    assert "1703" in out
    assert "индекс из кэша" in out
    assert "@@" not in out


def test_startup_noise_suppressed():
    for msg in (
        "Загружен кэш индекса: /path (страниц: 1703)",
        "Manual QA: 1 записей",
        "Bot username: @AnycubicWiki_bot",
    ):
        record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
        assert format_log_for_telegram(record) is None


def test_incoming_text_for_log_includes_reply_quote():
    class _User:
        id = 1

    class _Parent:
        text = "длинный вопрос про термистор"
        caption = None
        from_user = _User()
        message_id = 10

    class _Msg:
        reply_to_message = _Parent()
        text = "да, на скотч"
        caption = None
        message_id = 11
        message_thread_id = None

    out = incoming_text_for_log(_Msg(), "да, на скотч")
    assert "термистор" in out
    assert "скотч" in out
