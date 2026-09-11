"""Статистика: hourly = входящие, не только ответы бота."""
from __future__ import annotations

from app.bot.bot_stats import (
    _empty_stats,
    flush_bot_stats,
    get_hourly_activity,
    get_daily_distribution,
    get_peak_hours,
    get_stats_metrics,
    get_top_questions,
    get_top_wiki_pages,
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


def test_stats_persistence_is_throttled_and_flushable(tmp_path, monkeypatch):
    import json
    import app.bot.bot_stats as bs

    path = tmp_path / "bot_stats.json"
    monkeypatch.setattr(bs, "_stats_path", lambda: path)
    bd: dict = {}

    record_incoming_activity(bd, user_id=1)
    record_incoming_activity(bd, user_id=2)
    assert json.loads(path.read_text(encoding="utf-8"))["total_incoming"] == 1

    flush_bot_stats(bd)
    assert json.loads(path.read_text(encoding="utf-8"))["total_incoming"] == 2


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


def test_load_stats_rejects_oversized_file_before_json_decode(tmp_path, monkeypatch):
    import app.bot.bot_stats as bs

    path = tmp_path / "bot_stats.json"
    path.write_text("{}" * 20, encoding="utf-8")
    monkeypatch.setattr(bs, "_stats_path", lambda: path)
    monkeypatch.setattr(bs, "_MAX_STATS_CACHE_BYTES", 10)
    bd: dict = {}

    load_bot_stats(bd)

    assert bd["bot_stats"] == bs._empty_stats()


def test_load_keeps_valid_stats_when_one_value_is_corrupted(tmp_path, monkeypatch):
    import app.bot.bot_stats as bs

    p = tmp_path / "bot_stats.json"
    p.write_text(
        '{"wiki_pages":{"good":3,"bad":"broken"},"questions":{"q":2},'
        '"total_answers":"broken","total_incoming":4,"last_updated":"broken",'
        '"stats_version":2,"hourly_activity_kind":"incoming",'
        '"hourly_activity":[' + ",".join(["1"] * 24) + ']}',
        encoding="utf-8",
    )
    monkeypatch.setattr(bs, "_stats_path", lambda: p)
    bd: dict = {}

    load_bot_stats(bd)

    assert bd["bot_stats"]["wiki_pages"] == {"good": 3, "bad": 0}
    assert bd["bot_stats"]["questions"] == {"q": 2}
    assert bd["bot_stats"]["total_answers"] == 0
    assert bd["bot_stats"]["total_incoming"] == 4
    assert sum(bd["bot_stats"]["hourly_activity"]) == 24


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


def test_top_stats_returns_empty_for_non_positive_limit_and_keeps_ties():
    bd = {
        "bot_stats": {
            "wiki_pages": {"first": 3, "second": 3},
            "questions": {"q1": 2, "q2": 2},
        }
    }

    assert get_top_wiki_pages(bd, limit=0) == []
    assert get_top_questions(bd, limit=-1) == []
    assert get_top_wiki_pages(bd, limit=2) == [("first", 3), ("second", 3)]
    assert get_top_questions(bd, limit=2) == [("q1", 2), ("q2", 2)]


def test_readers_tolerate_corrupted_runtime_stats():
    bd = {
        "bot_stats": {
            "wiki_pages": {"good": "3", "bad": object(), 4: 99},
            "questions": "broken",
            "hourly_activity": ["2", object()] + [0] * 22,
            "total_answers": "bad",
            "total_incoming": "4",
            "user_messages": {"x": {"count": object()}, "bad": "broken"},
            "daily_activity": {"0": "5", "1": object()},
        }
    }

    assert get_top_wiki_pages(bd) == [("good", 3), ("bad", 0)]
    assert get_top_questions(bd) == []
    assert get_hourly_activity(bd)[:2] == [2, 0]
    assert get_stats_metrics(bd) == {
        "unique_questions": 0,
        "unique_users": 2,
        "answer_rate": 0,
        "avg_answers_per_user": 0,
    }
    assert get_peak_hours(bd, limit=0) == []
    assert get_daily_distribution(bd)["пн"] == 5
    assert get_daily_distribution(bd)["вт"] == 0


def test_writers_recover_corrupted_runtime_stats():
    bd = {
        "bot_stats": {
            "user_messages": "broken",
            "wiki_pages": [],
            "questions": "broken",
            "total_incoming": "bad",
            "total_answers": object(),
        }
    }

    record_incoming_activity(bd, user_id=42)
    record_answer(bd, url="https://wiki.example/x", question="как смазать", source="wiki")

    assert bd["bot_stats"]["total_incoming"] == 1
    assert bd["bot_stats"]["total_answers"] == 1
    assert bd["bot_stats"]["user_messages"]["42"]["count"] == 1
    assert bd["bot_stats"]["wiki_pages"] == {"https://wiki.example/x": 1}
    assert bd["bot_stats"]["questions"] == {"как смазать": 1}


def test_user_limit_handles_corrupted_entry_and_keeps_bounded_size(monkeypatch):
    import app.bot.bot_stats as bot_stats

    monkeypatch.setattr(bot_stats, "_persist", lambda *_args, **_kwargs: None)
    users = {str(i): {"user_id": i, "count": i} for i in range(bot_stats._MAX_TRACKED_USERS)}
    users["corrupted"] = "broken"
    bd = {"bot_stats": {"user_messages": users}}

    record_incoming_activity(bd, user_id=bot_stats._MAX_TRACKED_USERS + 1)

    assert len(bd["bot_stats"]["user_messages"]) == bot_stats._MAX_TRACKED_USERS
    assert "corrupted" not in bd["bot_stats"]["user_messages"]


def test_counter_limits_apply_on_load_and_runtime(monkeypatch, tmp_path):
    import json
    import app.bot.bot_stats as bot_stats

    monkeypatch.setattr(bot_stats, "_MAX_WIKI_PAGES", 2)
    monkeypatch.setattr(bot_stats, "_MAX_UNIQUE_QUESTIONS", 2)
    path = tmp_path / "bot_stats.json"
    path.write_text(
        json.dumps({
            "wiki_pages": {"low": 1, "mid": 2, "high": 3},
            "questions": {"low": 1, "mid": 2, "high": 3},
            "stats_version": 2,
            "hourly_activity_kind": "incoming",
            "hourly_activity": [0] * 24,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_stats, "_stats_path", lambda: path)
    loaded: dict = {}
    bot_stats.load_bot_stats(loaded)

    assert set(loaded["bot_stats"]["wiki_pages"]) == {"mid", "high"}
    assert set(loaded["bot_stats"]["questions"]) == {"mid", "high"}

    monkeypatch.setattr(bot_stats, "_persist", lambda *_args, **_kwargs: None)
    runtime: dict = {"bot_stats": bot_stats._empty_stats()}
    for _ in range(3):
        bot_stats.record_answer(runtime, url="high", question="high", source="wiki")
    for _ in range(2):
        bot_stats.record_answer(runtime, url="mid", question="mid", source="wiki")
    bot_stats.record_answer(runtime, url="low", question="low", source="wiki")

    assert set(runtime["bot_stats"]["wiki_pages"]) == {"mid", "high"}
    assert set(runtime["bot_stats"]["questions"]) == {"mid", "high"}
