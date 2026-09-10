from __future__ import annotations

import json

from app.bot.stores import _norm_text, _save_json_atomic


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
