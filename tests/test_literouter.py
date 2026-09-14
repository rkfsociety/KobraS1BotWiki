from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.bot.handlers import cmd_ii
from app.bot.handlers._cmd_ii import (
    _answer_body,
    _build_general_messages,
    _looks_truncated,
    _split_telegram_text,
)
from app.bot.literouter import LiteRouterError, ask_literouter
from app.web_wiki_index import WebWikiDoc, WebWikiIndex


def test_literouter_uses_openai_compatible_endpoint_and_parses_content(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "Готово"}}]}

        text = ""

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, endpoint, **kwargs):
            captured["endpoint"] = endpoint
            captured["kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr("app.bot.literouter.httpx.AsyncClient", FakeClient)

    result = asyncio.run(
        ask_literouter(
            api_key="secret-value",
            base_url="https://api.literouter.com/v1/",
            model="deepseek-v4-flash:free",
            messages=[{"role": "user", "content": "Привет"}],
            timeout_seconds=25,
            max_tokens=500,
        )
    )

    assert result == "Готово"
    assert captured["endpoint"] == "https://api.literouter.com/v1/chat/completions"
    assert captured["client_kwargs"] == {"timeout": 25, "follow_redirects": False}
    request_kwargs = captured["kwargs"]
    assert request_kwargs["headers"]["Authorization"] == "Bearer secret-value"
    assert request_kwargs["json"]["model"] == "deepseek-v4-flash:free"
    assert request_kwargs["json"]["stream"] is False
    assert request_kwargs["json"]["max_tokens"] == 500


def test_literouter_omits_max_tokens_when_unlimited(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "Готово"}}]}

        text = ""

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _endpoint, **kwargs):
            captured["json"] = kwargs["json"]
            return FakeResponse()

    monkeypatch.setattr("app.bot.literouter.httpx.AsyncClient", FakeClient)

    result = asyncio.run(
        ask_literouter(
            api_key="secret-value",
            base_url="https://api.literouter.com/v1",
            model="model",
            messages=[{"role": "user", "content": "Привет"}],
            timeout_seconds=25,
            max_tokens=None,
        )
    )

    assert result == "Готово"
    assert "max_tokens" not in captured["json"]


def test_literouter_rejects_non_https_base_url_without_request():
    try:
        asyncio.run(
            ask_literouter(
                api_key="secret-value",
                base_url="http://localhost/v1",
                model="model",
                messages=[],
                timeout_seconds=5,
                max_tokens=100,
            )
        )
    except Exception as exc:
        assert "https://" in str(exc)
    else:
        raise AssertionError("HTTP base URL must be rejected")


def _settings():
    return SimpleNamespace(
        literouter_enabled=True,
        literouter_api_key="secret-value",
        literouter_base_url="https://api.literouter.com/v1",
        literouter_models=("first-model", "second-model"),
        literouter_model="deepseek-v4-flash:free",
        literouter_timeout_seconds=25,
        literouter_max_tokens=500,
        literouter_context_docs=3,
        ru_layer_enabled=False,
        wiki_base_url="https://wiki.anycubic.com",
        ephemeral_exempt_chat_ids=frozenset(),
        reply_review_mention="off",
    )


def _update_for_ii(*, target=None):
    command = SimpleNamespace(
        text="/ii",
        caption=None,
        from_user=SimpleNamespace(id=7, language_code="ru"),
        reply_to_message=target,
        reply_text=AsyncMock(),
        chat_id=-100123,
        message_id=22,
        chat=SimpleNamespace(type="supergroup"),
        message_thread_id=None,
    )
    return SimpleNamespace(
        effective_message=command,
        effective_chat=SimpleNamespace(id=-100123, type="supergroup"),
        effective_user=command.from_user,
    )


def test_cmd_ii_requires_admin(monkeypatch):
    target = SimpleNamespace(text="Как прочистить сопло?", caption=None)
    update = _update_for_ii(target=target)
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings": _settings()}),
    )

    monkeypatch.setattr("app.bot.handlers._cmd_ii._deny_unless_admin_command_access", AsyncMock(return_value=True))

    asyncio.run(cmd_ii(update, context))

    update.effective_message.reply_text.assert_not_awaited()


def test_cmd_ii_requires_reply_to_user_message(monkeypatch):
    update = _update_for_ii()
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings": _settings()}),
    )

    monkeypatch.setattr("app.bot.handlers._cmd_ii._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_ii.schedule_delete_slash_command_and_reply", lambda **_kwargs: None)

    asyncio.run(cmd_ii(update, context))

    update.effective_message.reply_text.assert_awaited_once()
    assert "/ii" in update.effective_message.reply_text.await_args.args[0]


def test_cmd_ii_rejects_reply_to_bot_message(monkeypatch):
    target = SimpleNamespace(
        text="Предыдущий ответ бота",
        caption=None,
        from_user=SimpleNamespace(id=999, is_bot=True),
    )
    update = _update_for_ii(target=target)
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings": _settings()}),
    )

    monkeypatch.setattr("app.bot.handlers._cmd_ii._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_ii.schedule_delete_slash_command_and_reply", lambda **_kwargs: None)

    asyncio.run(cmd_ii(update, context))

    update.effective_message.reply_text.assert_awaited_once()
    assert "/ii" in update.effective_message.reply_text.await_args.args[0]


def test_cmd_ii_replies_to_target_and_includes_verified_wiki_source(monkeypatch):
    target_reply = AsyncMock(return_value=SimpleNamespace(message_id=99))
    target = SimpleNamespace(
        text="Как прочистить сопло?",
        caption=None,
        from_user=SimpleNamespace(id=42, is_bot=False),
        reply_text=target_reply,
        chat_id=-100123,
        message_id=21,
        message_thread_id=None,
        chat=SimpleNamespace(type="supergroup"),
    )
    update = _update_for_ii(target=target)
    settings = _settings()
    index = WebWikiIndex(
        [
            WebWikiDoc(
                title="Очистка сопла",
                url="https://wiki.anycubic.com/en/nozzle-cleaning",
                text="Снимите остатки пластика и очистите сопло.",
            )
        ]
    )
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings": settings, "wiki_index": index}),
    )

    monkeypatch.setattr("app.bot.handlers._cmd_ii._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_ii.ask_literouter", AsyncMock(return_value="WIKI_ANSWER Очистите сопло."))
    monkeypatch.setattr(
        "app.bot.handlers._cmd_ii.reply_for_user",
        AsyncMock(return_value=SimpleNamespace(message_id=99)),
    )
    monkeypatch.setattr("app.bot.handlers._cmd_ii._record_bot_answer_context", lambda **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii.add_to_recent_replies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii._record_stat", lambda *_args, **_kwargs: None)
    cleanup = Mock()
    monkeypatch.setattr("app.bot.handlers._cmd_ii.schedule_delete_slash_command_and_reply", cleanup)

    asyncio.run(cmd_ii(update, context))

    reply_for_user = __import__("app.bot.handlers._cmd_ii", fromlist=["reply_for_user"]).reply_for_user
    reply_for_user.assert_awaited_once()
    assert reply_for_user.await_args.args[0] is target
    body = reply_for_user.await_args.args[2]
    assert "Очистите сопло." in body
    assert "https://wiki.anycubic.com/en/nozzle-cleaning" in body
    cleanup.assert_not_called()


def test_cmd_ii_uses_next_model_after_provider_failure(monkeypatch):
    target = SimpleNamespace(
        text="Как прочистить сопло?",
        caption=None,
        from_user=SimpleNamespace(id=42, is_bot=False),
        chat_id=-100123,
        message_id=21,
        message_thread_id=None,
        chat=SimpleNamespace(type="supergroup"),
    )
    update = _update_for_ii(target=target)
    settings = _settings()
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings": settings}),
    )
    ask = AsyncMock(side_effect=[LiteRouterError("первая модель недоступна"), "Ответ резервной модели."])

    monkeypatch.setattr("app.bot.handlers._cmd_ii._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_ii.ask_literouter", ask)
    monkeypatch.setattr(
        "app.bot.handlers._cmd_ii.reply_for_user",
        AsyncMock(return_value=SimpleNamespace(message_id=99)),
    )
    monkeypatch.setattr("app.bot.handlers._cmd_ii._record_bot_answer_context", lambda **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii.add_to_recent_replies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii._record_stat", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii.schedule_delete_slash_command_and_reply", lambda **_kwargs: None)

    asyncio.run(cmd_ii(update, context))

    assert [call.kwargs["model"] for call in ask.await_args_list] == ["first-model", "second-model"]


def test_general_request_does_not_include_wiki_or_anycubic_prompt():
    messages = _build_general_messages("Скиньте инструкцию по смазке A1 Mini")

    assert "Anycubic" not in messages[0]["content"]
    assert "Bambu Lab A1 mini" in messages[0]["content"]
    assert "CONTEXT" not in messages[0]["content"]
    assert messages[1]["content"] == "Скиньте инструкцию по смазке A1 Mini"


def test_general_answer_does_not_keep_unasked_anycubic_brand():
    from app.bot.handlers._cmd_ii import _sanitize_general_answer

    result = _sanitize_general_answer(
        "Скиньте инструкцию по смазке A1 Mini",
        "GENERAL_ANSWER Это инструкция Anycubic A1 Mini.",
    )

    assert "Anycubic" not in result
    assert "производителя A1 Mini" in result


def test_general_answer_keeps_brand_when_user_asked_about_it():
    from app.bot.handlers._cmd_ii import _sanitize_general_answer

    result = _sanitize_general_answer(
        "Сравните Bambu A1 Mini и Anycubic Kobra.",
        "GENERAL_ANSWER Anycubic Kobra отличается конструкцией.",
    )

    assert "Anycubic Kobra" in result


def test_cmd_ii_retries_without_wiki_context_after_no_answer(monkeypatch):
    target = SimpleNamespace(
        text="Скиньте инструкцию по смазке A1 Mini",
        caption=None,
        from_user=SimpleNamespace(id=42, is_bot=False),
        chat_id=-100123,
        message_id=21,
        message_thread_id=None,
        chat=SimpleNamespace(type="supergroup"),
    )
    update = _update_for_ii(target=target)
    settings = _settings()
    index = WebWikiIndex(
        [
            WebWikiDoc(
                title="Нерелевантная статья Anycubic",
                url="https://wiki.anycubic.com/en/unrelated",
                text="Общие сведения о принтере.",
            )
        ]
    )
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={"settings": settings, "wiki_index": index}),
    )
    ask = AsyncMock(
        side_effect=[
            "NO_ANSWER В переданном контексте нет инструкции.",
            "GENERAL_ANSWER Для A1 Mini используйте инструкцию производителя по смазке направляющих.",
        ]
    )

    monkeypatch.setattr("app.bot.handlers._cmd_ii._deny_unless_admin_command_access", AsyncMock(return_value=False))
    monkeypatch.setattr("app.bot.handlers._cmd_ii.ask_literouter", ask)
    monkeypatch.setattr(
        "app.bot.handlers._cmd_ii.reply_for_user",
        AsyncMock(return_value=SimpleNamespace(message_id=99)),
    )
    monkeypatch.setattr("app.bot.handlers._cmd_ii._record_bot_answer_context", lambda **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii.add_to_recent_replies", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.bot.handlers._cmd_ii._record_stat", lambda *_args, **_kwargs: None)

    asyncio.run(cmd_ii(update, context))

    assert ask.await_count == 2
    assert "CONTEXT" in ask.await_args_list[0].kwargs["messages"][1]["content"]
    assert "Anycubic" not in ask.await_args_list[1].kwargs["messages"][0]["content"]
    reply = __import__("app.bot.handlers._cmd_ii", fromlist=["reply_for_user"]).reply_for_user
    assert "Для A1 Mini" in reply.await_args.args[2]


def test_answer_body_separates_source_lines():
    docs = [
        (SimpleNamespace(title="Первая статья", url="https://wiki.example/one"), 90),
        (SimpleNamespace(title="Вторая статья", url="https://wiki.example/two"), 80),
    ]

    body = _answer_body("WIKI_ANSWER Ответ.", docs)

    assert "https://wiki.example/one\n• Вторая статья" in body
    assert "https://wiki.example/one•" not in body


def test_answer_body_hides_sources_when_model_has_no_answer():
    docs = [(SimpleNamespace(title="Нерелевантная статья", url="https://wiki.example/no"), 20)]

    body = _answer_body("NO_ANSWER В вики нет подтверждённой информации.", docs)

    assert body == "🤖 В вики нет подтверждённой информации."
    assert "wiki.example" not in body


def test_answer_body_hides_wiki_sources_for_general_answer():
    docs = [(SimpleNamespace(title="Нерелевантная статья", url="https://wiki.example/no"), 20)]

    body = _answer_body("GENERAL_ANSWER Для светобокса обычно нужен корпус и источник света.", docs)

    assert body == "🤖 Для светобокса обычно нужен корпус и источник света."
    assert "wiki.example" not in body


def test_split_telegram_text_keeps_each_part_within_limit():
    parts = _split_telegram_text("слово " * 1000)

    assert len(parts) > 1
    assert all(0 < len(part) <= 4096 for part in parts)


def test_literouter_detects_incomplete_ending():
    assert _looks_truncated("Ответ обрывается, если") is True
    assert _looks_truncated("Ответ обрывается на фрагменте па") is True
    assert _looks_truncated("Ответ полностью закончен.") is False


def test_literouter_error_detail_does_not_expose_key(monkeypatch):
    class FakeResponse:
        status_code = 401
        text = "invalid key"

        def json(self):
            return {"error": {"message": "invalid key secret-value"}}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.bot.literouter.httpx.AsyncClient", FakeClient)

    try:
        asyncio.run(
            ask_literouter(
                api_key="secret-value",
                base_url="https://api.literouter.com/v1",
                model="model",
                messages=[],
                timeout_seconds=5,
                max_tokens=100,
            )
        )
    except Exception as exc:
        assert "secret-value" not in str(exc)
    else:
        raise AssertionError("HTTP failure must be raised")
