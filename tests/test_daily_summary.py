import app.bot.daily_summary as daily_summary
from app.bot.daily_summary import (
    CLOSING_PHRASES,
    OPENING_PHRASES,
)


def test_daily_summary_has_five_hundred_unique_openings_and_closings():
    assert len(OPENING_PHRASES) == 500
    assert len(CLOSING_PHRASES) == 500
    assert len(set(OPENING_PHRASES)) == 500
    assert len(set(CLOSING_PHRASES)) == 500


def test_daily_summary_chooses_phrases_on_each_call(monkeypatch):
    chosen = iter(
        [
            OPENING_PHRASES[1],
            CLOSING_PHRASES[2],
            OPENING_PHRASES[3],
            CLOSING_PHRASES[4],
        ]
    )
    monkeypatch.setattr(daily_summary.secrets, "choice", lambda _items: next(chosen))

    kwargs = {
        "day": "2026-09-14",
        "scope_label": "группе",
        "scope_key": "-100123:all",
        "total_incoming": 29,
        "topics": [("Настройка скоростей", 13)],
    }

    first = daily_summary.format_daily_summary(**kwargs)
    second = daily_summary.format_daily_summary(**kwargs)

    assert first != second
    assert "Всего было написано 29 сообщений" in first
    assert "Всего было написано 29 сообщений" in second
    assert "⚙️ Настройка скоростей (13 сообщений)" in first
