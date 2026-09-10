from __future__ import annotations

import app.bot.clarify as clarify


def test_sync_pending_ignores_corrupt_timestamps(monkeypatch):
    monkeypatch.setattr(
        clarify,
        "_load_clarify_store",
        lambda: {
            "1:2": {"ts": "broken", "question": "bad"},
            "3:4": {"ts": 20, "question": "new"},
        },
    )
    pending = {(3, 4): {"ts": 10, "question": "old"}}

    clarify._sync_clarify_pending_from_disk(pending)

    assert pending[(1, 2)]["question"] == "bad"
    assert pending[(3, 4)]["question"] == "new"


def test_safe_message_id_rejects_corrupted_values():
    assert clarify._safe_message_id("123") == 123
    assert clarify._safe_message_id("broken") is None
    assert clarify._safe_message_id(float("nan")) is None
