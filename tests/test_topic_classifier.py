from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.bot.chat_store import ChatStore
from app.bot.literouter import LiteRouterError
from app.bot.topic_classifier import _parse_result, classify_daily_topics, select_topic_models


def test_parse_result_recalculates_counts_from_source_indices() -> None:
    result = _parse_result(
        '{"topics":[{"title":"Сопло","count":999,"source_indices":[1,2]},'
        '{"title":"Повтор","source_indices":[2,3]}]}',
        {1: 2, 2: 1, 3: 4},
        limit=3,
    )

    assert result == [("Сопло", 3), ("Повтор", 4)]


def test_select_topic_models_uses_ranked_available_free_models(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.bot.topic_classifier.list_literouter_models",
        AsyncMock(
            return_value=(
                "glm-5.2:free",
                "deepseek-v4-flash:free",
                "paid-model",
                "configured-model",
            )
        ),
    )
    settings = SimpleNamespace(
        literouter_api_key="key",
        literouter_base_url="https://api.example/v1",
        literouter_timeout_seconds=25,
        literouter_cooldown_seconds=9,
        literouter_models=("configured-model",),
    )

    result = asyncio.run(select_topic_models(settings))

    assert result == ("deepseek-v4-flash:free", "glm-5.2:free", "configured-model")


def test_classify_daily_topics_reads_group_messages_and_saves_result(tmp_path, monkeypatch) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        messages = [
            "сопло стучит об заполнение",
            "сопло стучит об заполнение",
            "как настроить скорость печати",
            "как настроить скорость печати",
        ]
        for message_id, text in enumerate(messages, start=1):
            store.add_telegram_message(
                chat_id=-100,
                topic_id=7,
                telegram_message_id=message_id,
                user_id=message_id,
                text=text,
            )
        day = datetime.now(ZoneInfo("Europe/Kaliningrad")).date().isoformat()
        ask = AsyncMock(
            return_value=(
                '{"topics":['
                '{"title":"Сопло стучит об заполнение","source_indices":[1]},'
                '{"title":"Скорость печати","source_indices":[2]}],'
                '"excluded_count":0}'
            )
        )
        monkeypatch.setattr("app.bot.topic_classifier.ask_literouter", ask)
        settings = SimpleNamespace(
            literouter_enabled=True,
            literouter_api_key="key",
            literouter_base_url="https://api.example/v1",
            literouter_models=("test-model",),
            literouter_timeout_seconds=5,
            literouter_cooldown_seconds=0,
        )

        result = asyncio.run(
            classify_daily_topics(store, settings, chat_id=-100, day=day, limit=3)
        )

        assert result == [("Сопло стучит об заполнение", 2), ("Скорость печати", 2)]
        assert store.list_daily_topics(chat_id=-100, day=day) == result
        request = ask.await_args.kwargs["messages"]
        assert "сопло стучит об заполнение" in request[1]["content"]
        assert ask.await_args.kwargs["max_tokens"] is None
    finally:
        store.close()


def test_classify_daily_topics_tries_models_in_order_after_failure(tmp_path, monkeypatch) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        for message_id in (1, 2):
            store.add_telegram_message(
                chat_id=-100,
                topic_id=None,
                telegram_message_id=message_id,
                user_id=message_id,
                text="сопло стучит",
            )
        day = datetime.now(ZoneInfo("Europe/Kaliningrad")).date().isoformat()
        ask = AsyncMock(
            side_effect=[
                LiteRouterError("сетевой сбой: ReadTimeout"),
                '{"topics":[{"title":"Сопло","source_indices":[1]}]}',
            ]
        )
        monkeypatch.setattr("app.bot.topic_classifier.ask_literouter", ask)
        settings = SimpleNamespace(
            literouter_enabled=True,
            literouter_api_key="key",
            literouter_base_url="https://api.example/v1",
            literouter_timeout_seconds=5,
            literouter_cooldown_seconds=9,
            literouter_max_tokens=None,
        )

        result = asyncio.run(
            classify_daily_topics(
                store,
                settings,
                chat_id=-100,
                day=day,
                models=("first-model", "second-model"),
            )
        )

        assert result == [("Сопло", 2)]
        assert [call.kwargs["model"] for call in ask.await_args_list] == ["first-model", "second-model"]
    finally:
        store.close()
