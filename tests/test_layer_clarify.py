"""Слой/тест/печать без модели S1/2/3 — уточнение; обзорные URL вики — отклонение."""
from __future__ import annotations

from app.bot.layer_model_gate import (
    is_wiki_model_overview_url,
    model_specifically_identified,
    overview_url_penalty,
    topic_is_layer_slicing_intent,
    topic_requires_printer_model,
)
from app.bot.text_heuristics import _needs_model_clarification as needs_model_clarification_for
from app.bot.wiki_ranking import _response_wiki_url_acceptable as response_wiki_url_acceptable

_LAYER_QUESTION = "почему кобра на 0.16 слое спокойно пустила в печать тест"
_LAYER_S1 = "почему kobra s1 на 0.16 слое пустила в печать тест"
_KOBRA2_OVERVIEW = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-2"
_S1_FIRST_LAYER = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/first-layer"


def test_layer_question_needs_model_clarify():
    assert topic_is_layer_slicing_intent(_LAYER_QUESTION)
    assert topic_requires_printer_model(_LAYER_QUESTION)
    assert not model_specifically_identified(_LAYER_QUESTION)
    assert needs_model_clarification_for(_LAYER_QUESTION)


def test_layer_question_with_s1_no_clarify():
    assert topic_is_layer_slicing_intent(_LAYER_S1)
    assert model_specifically_identified(_LAYER_S1)
    assert not needs_model_clarification_for(_LAYER_S1)


def test_overview_url_rejected_for_layer_question():
    assert is_wiki_model_overview_url(_KOBRA2_OVERVIEW)
    assert not is_wiki_model_overview_url(_S1_FIRST_LAYER)
    assert overview_url_penalty(_LAYER_QUESTION, _KOBRA2_OVERVIEW) >= 70
    assert not response_wiki_url_acceptable(_LAYER_QUESTION, _KOBRA2_OVERVIEW)


def test_layer_s1_guide_acceptable():
    assert response_wiki_url_acceptable(_LAYER_S1, _S1_FIRST_LAYER)
