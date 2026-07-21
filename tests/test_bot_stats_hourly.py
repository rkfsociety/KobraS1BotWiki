"""Статистика: hourly = входящие, не только ответы бота."""
from __future__ import annotations

from app.bot.bot_stats import (
    _empty_stats,
    get_hourly_activity,
    get_top_users,
    load_bot_stats,
    record_answer,
    record_incoming_activity,
)


def test_incoming_bumps_hourly_and_user():
    bd: dict = {}
    record_incoming_activity(bd, user_id=42, username="alice", first_name="Alice")
    record_incoming_activity(bd, user_id=42, username="alice")
    record_incoming_activity(bd, user_id=7, first_name="Bob")
    hourly = get_hourly_activity(bd)
    assert sum(hourly) == 3
    assert bd["bot_stats"]["total_incoming"] == 3
    assert bd["bot_stats"]["total_answers"] == 0
    assert bd["bot_stats"]["user_messages"]["42"]["count"] == 2
    assert bd["bot_stats"]["user_messages"]["7"]["count"] == 1


def test_incoming_bumps_hourly_not_answers():
    bd: dict = {}
    record_incoming_activity(bd)
    record_incoming_activity(bd)
    hourly = get_hourly_activity(bd)
    assert sum(hourly) == 2
    assert bd["bot_stats"]["total_incoming"] == 2
    assert bd["bot_stats"]["total_answers"] == 0


def test_answer_does_not_bump_hourly():
    bd: dict = {"bot_stats": _empty_stats()}
    before = list(get_hourly_activity(bd))
    record_answer(bd, url="https://wiki.example/x", question="как смазать", source="wiki")
    assert get_hourly_activity(bd) == before
    assert bd["bot_stats"]["total_answers"] == 1
    assert bd["bot_stats"]["wiki_pages"]["https://wiki.example/x"] == 1


def test_load_migrates_old_hourly_to_empty_incoming(tmp_path, monkeypatch):
    import app.bot.bot_stats as bs

    p = tmp_path / "bot_stats.json"
    p.write_text(
        '{"wiki_pages":{},"questions":{},"hourly_activity":[0,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],'
        '"total_answers":5,"last_updated":1}',
        encoding="utf-8",
    )
    monkeypatch.setattr(bs, "_stats_path", lambda: p)
    bd: dict = {}
    load_bot_stats(bd)
    assert get_hourly_activity(bd) == [0] * 24
    assert bd["bot_stats"]["hourly_activity_kind"] == "incoming"
    assert bd["bot_stats"]["stats_version"] == 2


def test_get_top_users():
    bd: dict = {}
    for _ in range(5):
        record_incoming_activity(bd, user_id=1, username="top")
    for _ in range(2):
        record_incoming_activity(bd, user_id=2, username="mid")
    record_incoming_activity(bd, user_id=3)
    top = get_top_users(bd, limit=2)
    assert len(top) == 2
    assert top[0]["user_id"] == 1
    assert top[0]["count"] == 5
    assert top[1]["user_id"] == 2
