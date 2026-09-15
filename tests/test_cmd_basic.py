import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import cmd_id


def _run_cmd_id(*, is_forum, message_thread_id):
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="supergroup", id=-100123, is_forum=is_forum),
        effective_message=SimpleNamespace(
            reply_text=reply_text,
            message_thread_id=message_thread_id,
            from_user=SimpleNamespace(id=42, language_code="ru"),
            text="/id",
        ),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "settings": SimpleNamespace(wiki_base_url=""),
            }
        )
    )
    return reply_text, update, context


def test_cmd_id_shows_numeric_topic_id(monkeypatch):
    reply_text, update, context = _run_cmd_id(is_forum=True, message_thread_id=7)
    monkeypatch.setattr("app.bot.handlers._cmd_basic._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_basic.schedule_delete_slash_command_and_reply", lambda **_: None)
    monkeypatch.setattr("app.bot.handlers._cmd_basic.log_bot_reply_for_message", lambda *_, **__: None)

    asyncio.run(cmd_id(update, context))

    text = reply_text.await_args.args[0]
    assert "ID темы (topic_id, для ALLOWED_TOPIC_IDS): <code>7</code>" in text


def test_cmd_id_explains_general_topic_sentinel(monkeypatch):
    reply_text, update, context = _run_cmd_id(is_forum=True, message_thread_id=None)
    monkeypatch.setattr("app.bot.handlers._cmd_basic._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_basic.schedule_delete_slash_command_and_reply", lambda **_: None)
    monkeypatch.setattr("app.bot.handlers._cmd_basic.log_bot_reply_for_message", lambda *_, **__: None)

    asyncio.run(cmd_id(update, context))

    text = reply_text.await_args.args[0]
    assert "Telegram не передал числовой thread_id" in text
    assert "для ALLOWED_TOPIC_IDS используйте 0" in text
