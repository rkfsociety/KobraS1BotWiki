from __future__ import annotations

import json

from app.bot.user_context import _load_from_disk


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
