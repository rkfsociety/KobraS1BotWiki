from __future__ import annotations

import json
from pathlib import Path

from app.bot.bot_stats import _daily_epoch_bounds
from app.bot.chat_store import ChatStore
from scripts.migrate_legacy_data import migrate_legacy_data


def test_migration_keeps_aggregate_baseline_and_imports_only_available_samples(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "bot_stats.json").write_text(
        json.dumps(
            {
                "total_incoming": 10,
                "total_answers": 2,
                "hourly_activity": [10] + [0] * 23,
                "questions": {"старый вопрос": 3},
                "wiki_pages": {"https://wiki.example/old": 2},
                "user_messages": {"0": {"user_id": 0, "label": "old", "count": 10}},
                "daily_scopes": {
                    "2026-09-16:-100:all": {
                        "date": "2026-09-16",
                        "chat_id": -100,
                        "topic_id": None,
                        "total_incoming": 7,
                        "total_answers": 1,
                        "hourly_activity": [7] + [0] * 23,
                        "questions": {"старый вопрос": 2},
                        "wiki_pages": {"https://wiki.example/old": 1},
                        "user_messages": {"0": {"user_id": 0, "label": "old", "count": 7}},
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "data" / "missed_questions.json").write_text(
        json.dumps([{"chat_id": -100, "text": "новый образец", "ts": 1790000000}], ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / ".cache" / "recent_replies.json").write_text(
        json.dumps(
            [{
                "chat_id": -100,
                "question": "вопрос с ответом",
                "answer": "ответ",
                "source": "wiki",
                "url": "https://wiki.example/new",
                "ts": 1790000001,
            }],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = migrate_legacy_data(tmp_path)
    second = migrate_legacy_data(tmp_path)

    assert first["legacy_scopes"] == 1
    assert first["imported_missed_samples"] == 1
    assert first["imported_reply_samples"] == 2
    assert second["imported_missed_samples"] == 0
    assert second["imported_reply_samples"] == 0
    assert first["backup"]

    store = ChatStore(tmp_path / "data" / "chat.sqlite3")
    try:
        metrics = store.global_metrics()
        assert metrics["total_incoming"] == 10
        assert metrics["total_answers"] == 2
        assert metrics["questions"]["старый вопрос"] == 3
        start_ts, end_ts = _daily_epoch_bounds("2026-09-16")
        daily = store.daily_metrics(chat_id=-100, start_ts=start_ts, end_ts=end_ts)
        assert daily["total_incoming"] == 7
        assert daily["total_answers"] == 1
        assert {
            message.text
            for message in store.list_chat_messages(-100, 0, 2_000_000_000, role=None)
        } == {
            "новый образец",
            "вопрос с ответом",
            "ответ",
        }
    finally:
        store.close()
