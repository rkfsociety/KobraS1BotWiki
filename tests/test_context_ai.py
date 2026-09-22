from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.bot.chat_store import ChatMessage
from app.bot.context_ai import (
    build_contextual_answer_messages,
    build_question_classification_messages,
    classify_message_as_question,
    format_topic_context,
    generate_contextual_answer,
)


def _message(message_id: int, role: str, text: str, topic_id: int = 7) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        user_id=1,
        role=role,
        text=text,
        source="test",
        created_at=float(message_id),
        reply_to_id=None,
        chat_id=-100,
        topic_id=topic_id,
        telegram_message_id=message_id,
        first_name="Роман" if role == "user" else None,
    )


def test_context_prompt_contains_only_supplied_topic_history():
    context = format_topic_context([_message(1, "user", "Kobra S1 печатает с пропусками")])
    messages = build_contextual_answer_messages("а теперь что проверить?", context)

    assert "Kobra S1 печатает с пропусками" in messages[1]["content"]
    assert "другая тема" not in messages[1]["content"]
    assert "историю этой темы" in messages[0]["content"]


def test_question_classifier_returns_decision_without_generating_answer(monkeypatch):
    settings = SimpleNamespace(
        literouter_enabled=True,
        literouter_api_key="key",
        literouter_base_url="https://api.example/v1",
        literouter_models=("classifier:free",),
        literouter_timeout_seconds=5,
        literouter_cooldown_seconds=0,
    )
    calls: list[dict] = []

    async def ask(**kwargs):
        calls.append(kwargs)
        return "NOT_QUESTION"

    monkeypatch.setattr("app.bot.context_ai.ask_literouter", ask)

    decision = asyncio.run(classify_message_as_question(settings=settings, text="Что дверь не закрывалась"))

    assert decision is False
    assert calls[0]["model"] == "classifier:free"
    assert calls[0]["messages"] == build_question_classification_messages("Что дверь не закрывалась")


def test_contextual_answer_uses_only_free_models_and_fallback(monkeypatch):
    settings = SimpleNamespace(
        literouter_enabled=True,
        literouter_api_key="key",
        literouter_base_url="https://api.example/v1",
        literouter_models=("paid-model", "first:free", "second:free"),
        literouter_timeout_seconds=5,
        literouter_max_tokens=300,
        literouter_cooldown_seconds=0,
    )
    calls: list[str] = []

    async def ask(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "first:free":
            return "NO_ANSWER Точно ответить нельзя."
        return "AI_ANSWER Проверьте натяжение ремней."

    monkeypatch.setattr("app.bot.context_ai.ask_literouter", ask)

    answer, model, attempts = asyncio.run(
        generate_contextual_answer(
            settings=settings,
            question="что проверить?",
            topic_messages=[_message(1, "user", "Печать с пропусками")],
        )
    )

    assert calls == ["first:free", "second:free"]
    assert (answer, model, attempts) == ("Проверьте натяжение ремней.", "second:free", 2)
