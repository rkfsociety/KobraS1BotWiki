from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.bot.chat_store import ChatStore
from app.bot.topic_classifier import _parse_result, classify_daily_topics


def test_parse_result_recalculates_counts_from_source_indices() -> None:
    result = _parse_result(
        '{"topics":[{"title":"Сопло","count":999,"source_indices":[1,2]},'
        '{"title":"Повтор","source_indices":[2,3]}]}',
        {1: 2, 2: 1, 3: 4},
        limit=3,
    )

    assert result == [("Сопло", 3), ("Повтор", 4)]


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
