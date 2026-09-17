from __future__ import annotations

import json

from app.bot import state_store
from app.bot.chat_store import ChatStore


def test_legacy_state_is_imported_once_into_shared_database(tmp_path, monkeypatch):
    monkeypatch.setattr(state_store, "_project_root", lambda: tmp_path)
    store = ChatStore(tmp_path / "data" / "chat.sqlite3")
    monkeypatch.setattr(state_store, "shared_chat_store", lambda: store)
    legacy = tmp_path / "data" / "missed_questions.json"
    legacy.write_text(json.dumps([{"text": "старый вопрос"}], ensure_ascii=False), encoding="utf-8")

    try:
        is_db, value = state_store.load_state(
            "missed_questions", legacy, [], max_bytes=1024 * 1024
        )

        assert is_db is True
        assert value == [{"text": "старый вопрос"}]
        assert store.load_state("missed_questions") == value

        legacy.write_text("[]", encoding="utf-8")
        assert state_store.load_state(
            "missed_questions", legacy, [], max_bytes=1024 * 1024
        )[1] == value
    finally:
        store.close()
