from app.bot.daily_summary import (
    CLOSING_PHRASES,
    OPENING_PHRASES,
    format_daily_summary,
)


def test_daily_summary_has_fifty_unique_openings_and_closings():
    assert len(OPENING_PHRASES) == 50
    assert len(CLOSING_PHRASES) == 50
    assert len(set(OPENING_PHRASES)) == 50
    assert len(set(CLOSING_PHRASES)) == 50


def test_daily_summary_phrase_pair_is_stable_for_same_scope():
    kwargs = {
        "day": "2026-09-14",
        "scope_label": "группе",
        "scope_key": "-100123:all",
        "total_incoming": 29,
        "topics": [("Настройка скоростей", 13)],
    }

    first = format_daily_summary(**kwargs)
    second = format_daily_summary(**kwargs)

    assert first == second
    assert "Всего было написано 29 сообщений" in first
    assert "⚙️ Настройка скоростей (13 сообщений)" in first
