"""Статистика: hourly = входящие, не только ответы бота."""
from __future__ import annotations

from app.bot.bot_stats import (
    _empty_stats,
    get_hourly_activity,
    load_bot_stats,
    record_answer,
    record_incoming_activity,
)


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
