from __future__ import annotations

import json

from app.bot.stores import (
    _norm_text,
    _record_bot_answer_context,
    _save_json_atomic,
    flush_answer_ctx_store,
)


def test_save_json_atomic_replaces_file_without_leaving_temp_file(tmp_path):
    path = tmp_path / "nested" / "state.json"

    _save_json_atomic(path, {"answer": "готово"}, indent=2)

    assert json.loads(path.read_text(encoding="utf-8")) == {"answer": "готово"}
    assert list(path.parent.glob(".*.tmp")) == []


def test_norm_text_reuses_bounded_cache():
    _norm_text.cache_clear()

    assert _norm_text("  Принтер   S1  ") == "принтер s1"
    assert _norm_text("  Принтер   S1  ") == "принтер s1"

    info = _norm_text.cache_info()
    assert info.hits == 1
    assert info.currsize == 1


def test_save_json_atomic_uses_no_fixed_temp_name(tmp_path):
    path = tmp_path / "state.json"

    _save_json_atomic(path, {"value": 1})
    _save_json_atomic(path, {"value": 2})

    assert json.loads(path.read_text(encoding="utf-8"))["value"] == 2
    assert list(tmp_path.glob(".state.json.*.tmp")) == []


def test_answer_context_pruning_tolerates_malformed_entries(monkeypatch, tmp_path):
    class _App:
        bot_data = {
            "answer_ctx_store": {
                "bad": {"ts": "broken"},
                "not-a-dict": "broken",
            }
        }

    class _Context:
        application = _App()

    monkeypatch.setattr("app.bot.stores.ANSWER_CTX_STORE", tmp_path / "answer_context.json")
    monkeypatch.setattr("app.bot.stores._save_answer_ctx_store", lambda store, **kwargs: None)

    for index in range(801):
        _record_bot_answer_context(
            context=_Context(), chat_id=1, bot_message_id=index, query="q", url=None
        )

    assert len(_App.bot_data["answer_ctx_store"]) == 603


def test_answer_context_persistence_is_throttled_and_flushable(monkeypatch):
    import app.bot.stores as stores

    calls: list[dict] = []
    monkeypatch.setattr(stores, "_save_json_atomic", lambda path, data, **kwargs: calls.append(data))
    monkeypatch.setattr(stores.time, "time", lambda: 100.0)

    class _App:
        bot_data: dict = {}

    class _Context:
        application = _App()

    _record_bot_answer_context(context=_Context(), chat_id=1, bot_message_id=1, query="q", url=None)
    _record_bot_answer_context(context=_Context(), chat_id=1, bot_message_id=2, query="q", url=None)
    assert len(calls) == 1

    flush_answer_ctx_store(_App.bot_data)
    assert len(calls) == 2
