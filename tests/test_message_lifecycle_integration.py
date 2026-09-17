"""Интеграционные проверки маршрутизации сообщений и wiring lifecycle."""
from __future__ import annotations

import asyncio
import types
from datetime import datetime, timezone
from pathlib import Path

from telegram import Chat, Message, Update, User
from telegram.constants import ChatType

from app.bot.chat_store import ChatStore
from app.bot.handlers import _on_message as message_module
from app.bot.lifecycle import _register_handlers


class _Settings:
    allowed_chat_ids = None
    allowed_topic_ids = None
    require_can_reply = False
    reply_access_cache_seconds = 300
    clarify_enabled = False
    log_decisions = False
    log_all_messages = False
    require_trigger = False
    questions_only = True


class _Index:
    doc_count = 0

    @staticmethod
    def looks_like_question(_text: str) -> bool:
        return True


class _CountingIndex:
    doc_count = 0

    def __init__(self) -> None:
        self.looks_calls = 0

    def looks_like_question(self, _text: str) -> bool:
        self.looks_calls += 1
        return True


def _context() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        application=types.SimpleNamespace(
            bot_data={"settings": _Settings(), "wiki_index": _Index()}
        )
    )


def _update(text: str = "как настроить первый слой?", *, chat_type: str = "group") -> types.SimpleNamespace:
    user = types.SimpleNamespace(id=7, username="roman", first_name="Роман", is_bot=False, language_code="ru")
    message = types.SimpleNamespace(
        text=text,
        caption=None,
        message_thread_id=None,
        from_user=user,
        reply_to_message=None,
        message_id=10,
    )
    return types.SimpleNamespace(
        effective_message=message,
        effective_chat=types.SimpleNamespace(id=123, type=chat_type),
        effective_user=user,
        message=message,
    )


def _patch_message_side_effects(monkeypatch) -> None:
    monkeypatch.setattr(message_module, "_record_incoming", lambda *a, **k: None)
    monkeypatch.setattr(message_module, "_record_user_msg", lambda *a, **k: None)
    monkeypatch.setattr(message_module, "_enrich_ctx_query", lambda _bd, **kwargs: kwargs["query"])


def test_question_outside_allowed_context_is_collected_without_reply(monkeypatch):
    _patch_message_side_effects(monkeypatch)
    missed: list[dict] = []
    monkeypatch.setattr(message_module, "chat_topic_in_allowed_lists", lambda **kwargs: False)
    monkeypatch.setattr(message_module, "can_bot_reply_in_context", lambda **kwargs: False)
    monkeypatch.setattr(
        message_module,
        "add_missed_question",
        lambda **kwargs: missed.append(kwargs),
    )

    asyncio.run(message_module.on_message(_update(), _context()))

    assert len(missed) == 1
    assert missed[0]["text"] == "как настроить первый слой?"


def test_message_outside_allowed_topic_is_included_in_daily_stats(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(message_module, "_record_incoming", lambda *a, **kwargs: recorded.append(kwargs))
    monkeypatch.setattr(message_module, "chat_topic_in_allowed_lists", lambda **kwargs: False)
    monkeypatch.setattr(message_module, "can_bot_reply_in_context", lambda **kwargs: False)
    monkeypatch.setattr(message_module, "add_missed_question", lambda **kwargs: None)

    update = _update()
    update.effective_message.message_thread_id = 99
    asyncio.run(message_module.on_message(update, _context()))

    assert recorded[0]["topic_id"] == 99
    assert recorded[0]["track_daily"] is True


def test_any_update_persists_group_message_before_reply_filters(tmp_path: Path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        user = User(id=7, first_name="Роман", is_bot=False)
        chat = Chat(id=-100123, type=ChatType.SUPERGROUP)
        message = Message(
            message_id=10,
            date=datetime.now(timezone.utc),
            chat=chat,
            from_user=user,
            text="вопрос для общей базы",
        )
        update = Update(update_id=1, message=message)
        context = types.SimpleNamespace(
            application=types.SimpleNamespace(
                bot_data={"chat_store": store, "settings": _Settings()}
            )
        )

        asyncio.run(message_module.on_any_update(update, context))

        saved = store.list_chat_messages(-100123, 0, datetime.now(timezone.utc).timestamp() + 1)
        assert len(saved) == 1
        assert saved[0].text == "вопрос для общей базы"
        assert saved[0].chat_id == -100123
        assert saved[0].telegram_message_id == 10

        media = Message(
            message_id=11,
            date=datetime.now(timezone.utc),
            chat=chat,
            from_user=user,
        )
        asyncio.run(message_module.on_any_update(Update(update_id=2, message=media), context))
        saved = store.list_chat_messages(-100123, 0, datetime.now(timezone.utc).timestamp() + 1)
        assert len(saved) == 2
        assert saved[1].text == ""
    finally:
        store.close()


def test_chatter_is_filtered_before_search_or_reply(monkeypatch):
    _patch_message_side_effects(monkeypatch)
    monkeypatch.setattr(message_module, "chat_topic_in_allowed_lists", lambda **kwargs: True)
    async def can_process(*args, **kwargs):
        return True, None

    monkeypatch.setattr(message_module, "should_process_incoming_wiki_message", can_process)
    monkeypatch.setattr(message_module, "can_bot_reply_in_context", lambda **kwargs: True)
    monkeypatch.setattr(message_module, "_is_conversational_chatter", lambda _text: True)
    monkeypatch.setattr(message_module, "_try_reply_manual_qa", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))

    asyncio.run(message_module.on_message(_update("запустил первый слой, вроде печатает"), _context()))


def test_manual_answer_route_is_reached_after_message_gates(monkeypatch):
    _patch_message_side_effects(monkeypatch)
    monkeypatch.setattr(message_module, "chat_topic_in_allowed_lists", lambda **kwargs: True)
    async def can_process(*args, **kwargs):
        return True, None

    monkeypatch.setattr(message_module, "should_process_incoming_wiki_message", can_process)
    monkeypatch.setattr(message_module, "can_bot_reply_in_context", lambda **kwargs: True)
    monkeypatch.setattr(message_module, "_is_conversational_chatter", lambda _text: False)
    calls: list[str] = []

    async def manual(*args, **kwargs):
        calls.append(kwargs["query_text"])
        return True

    monkeypatch.setattr(message_module, "_try_reply_manual_qa", manual)

    asyncio.run(message_module.on_message(_update(), _context()))

    assert calls == ["как настроить первый слой?"]


def test_private_question_is_processed_even_when_group_allowlist_is_configured(monkeypatch):
    _patch_message_side_effects(monkeypatch)
    monkeypatch.setattr(message_module, "can_bot_reply_in_context", lambda **kwargs: True)
    calls: list[str] = []

    async def manual(*args, **kwargs):
        calls.append(kwargs["query_text"])
        return True

    monkeypatch.setattr(message_module, "_try_reply_manual_qa", manual)
    context = _context()
    settings = context.application.bot_data["settings"]
    settings.allowed_chat_ids = frozenset({-100123})
    settings.allowed_topic_ids = frozenset({42})
    settings.require_can_reply = True

    asyncio.run(message_module.on_message(_update(chat_type=ChatType.PRIVATE), context))

    assert calls == ["как настроить первый слой?"]


def test_question_classification_is_reused_between_message_gates(monkeypatch):
    _patch_message_side_effects(monkeypatch)
    monkeypatch.setattr(message_module, "chat_topic_in_allowed_lists", lambda **kwargs: True)

    async def can_process(*args, **kwargs):
        return True, None

    monkeypatch.setattr(message_module, "should_process_incoming_wiki_message", can_process)
    monkeypatch.setattr(message_module, "can_bot_reply_in_context", lambda **kwargs: True)
    monkeypatch.setattr(message_module, "_is_triggered_message", lambda *args, **kwargs: False)
    monkeypatch.setattr(message_module, "_reply_is_expected_by_bot", lambda *args, **kwargs: False)
    monkeypatch.setattr(message_module, "_is_conversational_chatter", lambda _text: False)

    async def manual(*args, **kwargs):
        return True

    monkeypatch.setattr(message_module, "_try_reply_manual_qa", manual)
    context = _context()
    context.application.bot_data["settings"].require_trigger = True
    index = _CountingIndex()
    context.application.bot_data["wiki_index"] = index

    asyncio.run(message_module.on_message(_update(), context))

    assert index.looks_calls == 1


def test_lifecycle_registers_commands_update_and_message_handlers_in_order():
    class _App:
        def __init__(self) -> None:
            self.handlers: list[tuple[object, int | None]] = []
            self.errors: list[object] = []

        def add_handler(self, handler, group=None):
            self.handlers.append((handler, group))

        def add_error_handler(self, callback):
            self.errors.append(callback)

    app = _App()
    _register_handlers(app)

    callbacks = [getattr(handler, "callback", None).__name__ for handler, _ in app.handlers]
    assert callbacks[:15] == [
        "cmd_start", "cmd_help", "cmd_id", "cmd_admincheck", "cmd_app", "cmd_wiki",
        "cmd_ii", "cmd_ping", "cmd_status", "cmd_stats", "cmd_error", "cmd_fix", "cmd_qaadd",
        "cmd_qalist", "cmd_qadel",
    ]
    assert "on_channel_command" in callbacks
    assert "on_any_update" in callbacks
    assert "on_message" in callbacks
    assert "on_message_reaction" in callbacks
    assert app.handlers[callbacks.index("on_any_update")][1] == -1
    assert app.errors == [message_module.on_error]
