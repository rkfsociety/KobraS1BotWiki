from __future__ import annotations

import json

from app.bot.stores import (
    _norm_text,
    _get_answer_ctx_store,
    _save_interval_elapsed,
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


def test_save_interval_treats_corrupted_timestamp_as_due_once():
    assert _save_interval_elapsed(float("nan"), now=100.0, interval=60.0)
    assert not _save_interval_elapsed(100.0, now=120.0, interval=60.0)
    assert _save_interval_elapsed(100.0, now=160.0, interval=60.0)


def test_answer_context_accessor_loads_disk_only_when_missing(monkeypatch):
    calls: list[int] = []
    loaded = {"one": {"q": "q"}}
    monkeypatch.setattr(
        "app.bot.stores._load_answer_ctx_store",
        lambda: calls.append(1) or loaded,
    )
    bot_data: dict = {"answer_ctx_store": {"cached": {"q": "cached"}}}

    assert _get_answer_ctx_store(bot_data)["cached"]["q"] == "cached"
    assert calls == []

    bot_data.pop("answer_ctx_store")
    assert _get_answer_ctx_store(bot_data) is loaded
    assert calls == [1]


def test_answer_context_loader_discards_malformed_and_old_entries(monkeypatch, tmp_path):
    import app.bot.stores as stores

    payload = {
        "bad": "not-a-record",
        **{str(index): {"ts": index, "q": "q"} for index in range(900)},
    }
    path = tmp_path / "answer-context.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(stores, "ANSWER_CTX_STORE", path)

    result = stores._load_answer_ctx_store()

    assert len(result) == stores._MAX_ANSWER_CTX_ENTRIES
    assert "bad" not in result
    assert "0" not in result
    assert "899" in result


def test_clarify_loader_discards_malformed_and_old_entries(monkeypatch, tmp_path):
    import app.bot.stores as stores

    payload = {
        "bad": "not-a-record",
        **{str(index): {"ts": index, "original": "q"} for index in range(1100)},
    }
    path = tmp_path / "clarify-pending.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(stores, "CLARIFY_STORE", path)

    result = stores._load_clarify_store()

    assert len(result) == stores._MAX_CLARIFY_ENTRIES
    assert "bad" not in result
    assert "0" not in result
    assert "1099" in result


def test_fix_loader_bounds_entries_and_normalizes_values(monkeypatch, tmp_path):
    import app.bot.stores as stores

    payload = {
        "bad": 7,
        **{str(index): f"  https://example.test/{index}  " for index in range(900)},
    }
    path = tmp_path / "fixes.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(stores, "FIX_STORE", path)

    result = stores._load_fix_store()

    assert len(result) == stores._MAX_FIX_ENTRIES
    assert "bad" not in result
    assert "0" not in result
    assert result["899"] == "https://example.test/899"


def test_feedback_loader_bounds_queries_and_urls(monkeypatch, tmp_path):
    import app.bot.stores as stores

    payload = {
        "bad": "not-a-list",
        **{
            str(index): [f"https://example.test/{item}" for item in range(25)]
            for index in range(2100)
        },
    }
    path = tmp_path / "feedback.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(stores, "FEEDBACK_STORE", path)

    result = stores._load_feedback_store()

    assert len(result) == stores._MAX_FEEDBACK_ENTRIES
    assert "bad" not in result
    assert "0" not in result
    assert result["2099"] == [f"https://example.test/{item}" for item in range(5, 25)]


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

    assert len(_App.bot_data["answer_ctx_store"]) == 601


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


def test_answer_context_throttling_recovers_from_non_finite_timestamp(monkeypatch):
    import app.bot.stores as stores

    calls: list[dict] = []
    monkeypatch.setattr(stores, "_save_json_atomic", lambda path, data, **kwargs: calls.append(data))
    monkeypatch.setattr(stores.time, "time", lambda: 100.0)
    bot_data = {"_answer_ctx_last_save": float("nan")}

    stores._save_answer_ctx_store({}, bot_data=bot_data)
    stores._save_answer_ctx_store({}, bot_data=bot_data)

    assert len(calls) == 1
