from __future__ import annotations

import json

from app.bot.user_context import (
    _prune_context_store,
    _load_from_disk,
    enrich_query,
    get_user_topic_hint,
    record_bot_answer,
    record_user_message,
)


def test_context_store_pruning_keeps_most_recent_keys():
    store = {
        "old": [{"ts": 10, "text": "old"}],
        "new": [{"ts": 30, "text": "new"}],
        "middle": [{"ts": 20, "text": "middle"}],
    }

    _prune_context_store(store, max_keys=2)

    assert set(store) == {"new", "middle"}


def test_load_context_skips_bad_timestamps_and_duplicate_records(tmp_path, monkeypatch):
    path = tmp_path / "user_ctx.json"
    path.write_text(json.dumps({
        "users": {
            "chat:user": [
                {"ts": "not-a-number", "text": "broken"},
                {"ts": 999, "text": "valid"},
                {"ts": 999, "text": "duplicate"},
            ]
        },
        "bot_answers": {},
    }), encoding="utf-8")
    monkeypatch.setattr("app.bot.user_context._ctx_path", lambda: path)
    monkeypatch.setattr("app.bot.user_context.time.time", lambda: 1000.0)
    bot_data = {"user_ctx_msgs": {"chat:user": [None, {"ts": 999, "text": "existing"}]}}

    _load_from_disk(bot_data)

    assert bot_data["user_ctx_msgs"]["chat:user"] == [
        {"ts": 999, "text": "existing"},
    ]


def test_runtime_context_methods_skip_malformed_timestamps():
    bot_data = {
        "_user_ctx_loaded": True,
        "user_ctx_msgs": {"20:10": [{"ts": ["bad"], "text": "старое"}]},
        "user_ctx_answers": {"20:10": [{"ts": "bad", "text": "ответ"}]},
        "chat_ctx_msgs": {"20": [{"ts": {"bad": True}, "user_id": 99, "text": "чат"}]},
    }

    record_user_message(bot_data, user_id=10, chat_id=20, text="новый вопрос")
    record_bot_answer(bot_data, user_id=10, chat_id=20, answer_text="ответ", url="")

    assert enrich_query(bot_data, user_id=10, chat_id=20, query="это") == "это"
    assert get_user_topic_hint(bot_data, user_id=10, chat_id=20) == "ответ / новый / вопрос"


def test_runtime_context_recovers_from_corrupted_store_containers():
    bot_data = {
        "_user_ctx_loaded": True,
        "user_ctx_msgs": "broken",
        "user_ctx_answers": [],
        "chat_ctx_msgs": None,
    }

    record_user_message(bot_data, user_id=10, chat_id=20, text="новый вопрос")
    record_bot_answer(bot_data, user_id=10, chat_id=20, answer_text="ответ", url="")

    assert bot_data["user_ctx_msgs"]["20:10"][-1]["text"] == "новый вопрос"
    assert bot_data["user_ctx_answers"]["20:10"][-1]["text"] == "ответ"
    assert bot_data["chat_ctx_msgs"]["20"][-1]["user_id"] == 10
