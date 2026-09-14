import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.bot_stats import record_answer, record_incoming_activity
from app.bot.handlers import cmd_app, cmd_stats
from app.bot.panel_login import cmd_start


def test_cmd_app_publishes_direct_miniapp_button():
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="supergroup", id=-100123),
        effective_message=SimpleNamespace(reply_text=reply_text),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "bot_username": "kobra_help_bot",
                "settings": SimpleNamespace(developer_user_ids=[]),
            }
        ),
        bot=SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="administrator")
            )
        ),
    )

    asyncio.run(cmd_app(update, context))

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "📱 Открыть приложение"
    assert button.url == "https://t.me/kobra_help_bot?startapp"


def test_start_app_payload_opens_miniapp_button():
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply_text),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        args=["app"],
        application=SimpleNamespace(
            bot_data={"settings": SimpleNamespace(panel_webapp_url="https://example.test/app")}
        ),
    )

    asyncio.run(cmd_start(update, context))

    kwargs = reply_text.await_args.kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.web_app.url == "https://example.test/app"


def test_cmd_stats_in_private_chat_uses_configured_group(monkeypatch):
    reply_text = AsyncMock()
    monkeypatch.setattr("app.bot.handlers._cmd_status.schedule_delete_slash_command_and_reply", lambda **_: None)
    monkeypatch.setattr("app.bot.handlers._cmd_status.log_bot_reply_for_message", lambda *_, **__: None)
    bot_data = {
        "settings": SimpleNamespace(panel_admin_chat_id=-100123, wiki_base_url=""),
    }
    record_incoming_activity(bot_data, chat_id=-100123, topic_id=7, user_id=42)
    record_incoming_activity(bot_data, chat_id=-100123, topic_id=7, user_id=43)
    record_answer(
        bot_data,
        url="https://wiki.example/speed",
        question="как скорости",
        source="wiki",
        chat_id=-100123,
        topic_id=7,
        topic="Настройка скоростей",
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private", id=42),
        effective_message=SimpleNamespace(reply_text=reply_text, message_thread_id=None),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data=bot_data), args=[])

    asyncio.run(cmd_stats(update, context))

    text = reply_text.await_args.args[0]
    assert "группе" in text
    assert "Всего было написано 2 сообщений" in text
    assert "⚙️ Настройка скоростей (2 сообщений)" in text


def test_cmd_stats_in_group_topic_requires_allowed_reply_context(monkeypatch):
    reply_text = AsyncMock()
    member = SimpleNamespace(status="administrator")
    bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=member))
    monkeypatch.setattr("app.bot.handlers._cmd_status.schedule_delete_slash_command_and_reply", lambda **_: None)
    monkeypatch.setattr("app.bot.handlers._cmd_status.log_bot_reply_for_message", lambda *_, **__: None)
    bot_data = {
        "bot_id": 900,
        "settings": SimpleNamespace(
            panel_admin_chat_id=-100123,
            developer_user_ids=frozenset(),
            allowed_chat_ids=frozenset({-100123}),
            allowed_topic_ids=frozenset({7}),
            wiki_base_url="",
        ),
    }
    record_incoming_activity(bot_data, chat_id=-100123, topic_id=7, user_id=42)
    record_answer(
        bot_data,
        url="https://wiki.example/hotend",
        question="хотэнд",
        source="wiki",
        chat_id=-100123,
        topic_id=7,
        topic="Обсуждение стокового хотэнда",
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="supergroup", id=-100123, is_forum=True),
        effective_message=SimpleNamespace(reply_text=reply_text, message_thread_id=7, from_user=SimpleNamespace(id=42)),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(application=SimpleNamespace(bot_data=bot_data), bot=bot, args=[])

    asyncio.run(cmd_stats(update, context))

    assert "Обсуждение стокового хотэнда (1 сообщений)" in reply_text.await_args.args[0]
