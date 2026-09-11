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


def test_runtime_dict_recovers_corrupted_clarify_container():
    bot_data = {"clarify_pending": ["broken"]}

    result = clarify._runtime_dict(bot_data, "clarify_pending")

    assert result == {}
    assert bot_data["clarify_pending"] is result


def test_pending_pruning_keeps_newest_entries(monkeypatch):
    pending = {
        (0, 0): {"ts": 1},
        (1, 1): {"ts": 2},
        (2, 2): {"ts": 3},
    }
    monkeypatch.setattr(clarify, "_MAX_PENDING_CLARIFICATIONS", 2)

    clarify._prune_pending_clarifications(pending)

    assert set(pending) == {(1, 1), (2, 2)}
