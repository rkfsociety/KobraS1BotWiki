"""Интеграционные проверки маршрутизации сообщений и wiring lifecycle."""
from __future__ import annotations

import asyncio
import types

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


def _context() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        application=types.SimpleNamespace(
            bot_data={"settings": _Settings(), "wiki_index": _Index()}
        )
    )


def _update(text: str = "как настроить первый слой?") -> types.SimpleNamespace:
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
        effective_chat=types.SimpleNamespace(id=123),
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
    assert callbacks[:14] == [
        "cmd_start", "cmd_help", "cmd_id", "cmd_admincheck", "cmd_app", "cmd_wiki",
        "cmd_ping", "cmd_status", "cmd_error", "cmd_fix", "cmd_qaadd", "cmd_qalist",
        "cmd_qadel", "cmd_update",
    ]
    assert "on_channel_command" in callbacks
    assert "on_any_update" in callbacks
    assert "on_message" in callbacks
    assert "on_message_reaction" in callbacks
    assert app.handlers[15][1] == -1
    assert app.errors == [message_module.on_error]
