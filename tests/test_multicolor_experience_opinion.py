"""Мнение/сравнение про смену цвета в многоцвете — не вопрос к вики."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_multicolor_experience_opinion,
    _is_non_wiki_chatter_message,
)

_MSG = (
    "попозже протестирую в многоцвет его. но мне как минимум на иксе нравится "
    "более тихая смена цвета. кобра 3 меняет цвета своим какахометом какбудто "
    "затвор калаша передергивается"
)


def test_color_change_opinion_suppressed():
    assert _is_multicolor_experience_opinion(_MSG)
    assert _is_non_wiki_chatter_message(_MSG)


def test_real_color_questions_not_suppressed():
    for msg in (
        "Как настроить смену цвета на кобре 3?",
        "Как сделать многоцветную печать?",
        "кобра громко меняет цвет, это нормально?",
        "хочу настроить смену цвета подскажите",
    ):
        assert not _is_multicolor_experience_opinion(msg), msg
