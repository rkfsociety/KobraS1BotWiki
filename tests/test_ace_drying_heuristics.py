"""ACE Pro как сушилка филамента — не гайд замены катушки."""
from __future__ import annotations

from app.bot.text_heuristics import _topic_is_ace_filament_drying_intent
from app.bot.wiki_ranking import _response_wiki_url_acceptable, _topic_path_bonus
from app.ru_layer import expand_queries

_QUESTION = "Аськи как сушилки"
_BAD_URL = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/ace-pro-filament-replacement-guide"
)
_NOTES_URL = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/ace-pro-notes"


def test_ace_drying_intent_detected():
    assert _topic_is_ace_filament_drying_intent(_QUESTION)


def test_filament_replacement_rejected_for_drying_question():
    assert not _response_wiki_url_acceptable(_QUESTION, _BAD_URL)


def test_notes_acceptable_for_drying_question():
    assert _response_wiki_url_acceptable(_QUESTION, _NOTES_URL)


def test_path_bonus_prefers_notes_over_replacement():
    b_notes = _topic_path_bonus(_QUESTION, _NOTES_URL)
    b_bad = _topic_path_bonus(_QUESTION, _BAD_URL)
    assert b_notes > b_bad


def test_expand_queries_adds_drying_hint():
    variants = expand_queries(_QUESTION)
    assert any("drying" in v.lower() or "moisture" in v.lower() for v in variants)
