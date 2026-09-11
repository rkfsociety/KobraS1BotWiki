"""Опрос собеседников об их опыте («ты замерял?», «прошивку ставили?») — не вопрос боту."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_non_wiki_chatter_message,
    _is_peer_action_experience_question,
)


def test_peer_resonance_question_suppressed():
    msg = "А ты после замены, замерял резонанс? Изменился? но ля резонирует при печати"
    assert _is_peer_action_experience_question(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_bare_firmware_question_suppressed():
    msg = "Прошивку 2.7.2.7 ставили?"
    assert _is_peer_action_experience_question(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_group_addressed_short_questions():
    assert _is_peer_action_experience_question("Сопло меняли?")
    assert _is_peer_action_experience_question("А вы калибровали стол?")


def test_peer_action_question_reuses_cached_classification():
    text = "Сопло меняли?"
    _is_peer_action_experience_question.cache_clear()
    before = _is_peer_action_experience_question.cache_info()
    assert _is_peer_action_experience_question(text)
    middle = _is_peer_action_experience_question.cache_info()
    assert _is_peer_action_experience_question(text)
    after = _is_peer_action_experience_question.cache_info()
    assert middle.misses == before.misses + 1
    assert after.hits == middle.hits + 1


def test_real_help_requests_not_suppressed():
    for msg in (
        "Как поставить прошивку 2.7.2.7?",
        "Нужно ли ставить прошивку 2.7.2.7?",
        "Поменял сопло, теперь не печатает, что делать?",
        "Какую прошивку ставить на кобру?",
        "Как замерить резонанс?",
        "У меня резонирует при печати, подскажите?",
    ):
        assert not _is_peer_action_experience_question(msg), msg
