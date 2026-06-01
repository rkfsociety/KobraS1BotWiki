"""Зеркало лога в Telegram: только ответы бота с текстом вопроса и ответа."""
from __future__ import annotations

import logging

from app.bot.decision_log import incoming_text_for_log, telegram_message_link
from app.bot.telegram_log_mirror import LOG_MIRROR_TEXT_MAX, format_log_for_telegram


def test_log_mirror_text_max_reasonable():
    assert LOG_MIRROR_TEXT_MAX >= 500


def test_telegram_message_link_supergroup():
    url = telegram_message_link(-1002295062981, 42)
    assert url == "https://t.me/c/2295062981/42"


def test_telegram_message_link_with_thread():
    url = telegram_message_link(-1002295062981, 99, thread_id=7)
    assert url == "https://t.me/c/2295062981/7/99"


def test_seen_not_mirrored():
    msg = (
        "seen chat=-1002295062981 user=42 has_reply=false reply_mid=None reply_from=None "
        "mid=12345 thread=None text=привет"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    assert format_log_for_telegram(record) is None


def test_skip_not_mirrored():
    for reason in (
        "not_triggered",
        "not_a_question",
        "low_score",
        "cooldown",
    ):
        msg = f"skip chat=-1001 reason={reason} mid=99 user=42"
        record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
        assert format_log_for_telegram(record) is None, reason


def test_incoming_message_not_mirrored():
    msg = "Входящее сообщение chat=-1001 user=42: как смазать"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    assert format_log_for_telegram(record) is None


def test_clarify_line_not_mirrored():
    msg = "clarify chat=-1001 score=80 url=https://wiki.example/x reason=model_required mid=99 thread=None"
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    assert format_log_for_telegram(record) is None


def test_bot_reply_shows_user_and_reply_text():
    msg = (
        "bot_reply kind=wiki chat=-1001 user=42 mid=123 message_id=456 "
        "score=80 url=https://wiki.example/x "
        "user_text=как смазать подшипник reply_text=Уже есть в вики · ссылка"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    # новый формат: иконка ✅ + тип, без «Ответ бота» в заголовке
    assert "✅" in out
    assert "отправлена ссылка" in out
    assert "как смазать" in out
    assert "Уже есть в вики" in out
    assert "https://t.me/c/" in out
    assert "📊" in out  # score
    assert "80" in out


def test_bot_reply_shows_trigger_and_model():
    msg = (
        "bot_reply kind=wiki chat=-1001 user=42 mid=123 message_id=456 "
        "score=100 url=https://wiki.example/kobra-s1-combo/firmware-update-guide "
        "trigger=auto model=kobra-s1-combo "
        "user_text=есть ссылка на прошивку reply_text=Уже есть в вики"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    # источник запроса показан человекочитаемо
    assert "авто-вопрос" in out
    # модель принтера видна в хвосте
    assert "🖨" in out
    assert "kobra-s1-combo" in out


def test_bot_reply_mention_trigger_label():
    msg = (
        "bot_reply kind=wiki chat=-1001 user=42 mid=1 message_id=2 "
        "score=90 url=https://wiki.example/x trigger=mention "
        "user_text=@bot как смазать reply_text=ответ"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "упоминание" in out


def test_bot_reply_legacy_query_field():
    msg = (
        "bot_reply kind=manual_qa_message chat=-1001 user=42 "
        "query=термистор reply_text=Ответ из QA"
    )
    record = logging.LogRecord("root", logging.INFO, "", 0, msg, (), None)
    out = format_log_for_telegram(record)
    assert out is not None
    assert "термистор" in out
    assert "Ответ из QA" in out


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
