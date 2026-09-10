from __future__ import annotations

import json

from app.bot.stores import _save_json_atomic


def test_save_json_atomic_replaces_file_without_leaving_temp_file(tmp_path):
    path = tmp_path / "nested" / "state.json"

    _save_json_atomic(path, {"answer": "готово"}, indent=2)

    assert json.loads(path.read_text(encoding="utf-8")) == {"answer": "готово"}
    assert list(path.parent.glob(".*.tmp")) == []
