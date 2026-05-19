"""Бытовые реплики в чате — бот не должен отвечать и не должен уточнять модель."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _message_has_help_intent,
    _needs_model_clarification,
)
from app.web_wiki_index import _looks_like_question

_BED_COMPARE_MSG = "Разберемся, тут кстати стол регулируется не сверху как на кобре"

_LINK_REQUEST = "Пасаны киньте ссыль на вики кубов по настройке стола чот лох не могу найти"

_LINK_WITH_MODEL = "киньте ссыль на вики кубов по настройке стола для kobra s1"

_REAL_QUESTION = "как откалибровать стол на kobra s1 combo?"

_THERMISTOR_OBSERVATION = "Это они термистор чтоли чисто на скотч приклеили"

_THERMISTOR_HELP = "у меня термистор отвалился на kobra s1, что делать?"


def test_bed_compare_other_printer_is_chatter():
    assert _is_conversational_chatter(_BED_COMPARE_MSG)
    assert not _looks_like_question(_BED_COMPARE_MSG)


def test_link_request_still_question_and_needs_model():
    assert not _is_conversational_chatter(_LINK_REQUEST)
    assert _looks_like_question(_LINK_REQUEST)
    assert _needs_model_clarification(_LINK_REQUEST)


def test_link_with_model_still_question_no_clarify():
    assert not _is_conversational_chatter(_LINK_WITH_MODEL)
    assert _looks_like_question(_LINK_WITH_MODEL)
    assert not _needs_model_clarification(_LINK_WITH_MODEL)


def test_comparative_kak_alone_not_help_intent():
    assert not _message_has_help_intent("стол не сверху как на кобре")


def test_real_how_to_question_has_help_intent():
    assert _message_has_help_intent(_REAL_QUESTION)
    assert _looks_like_question(_REAL_QUESTION)
    assert not _is_conversational_chatter(_REAL_QUESTION)


def test_thermistor_third_party_observation_is_chatter():
    assert _is_conversational_chatter(_THERMISTOR_OBSERVATION)
    assert not _looks_like_question(_THERMISTOR_OBSERVATION)


def test_thermistor_help_request_not_chatter():
    assert not _is_conversational_chatter(_THERMISTOR_HELP)
    assert _looks_like_question(_THERMISTOR_HELP)


def test_chtoli_does_not_trigger_what_substring():
    assert not _looks_like_question("термистор чтоли на скотч")


_CHITI_BOX_NOISE = "Но чиди бокс шумит просто ужас как 😂"


def test_chiti_box_noise_complaint_is_chatter():
    assert _is_conversational_chatter(_CHITI_BOX_NOISE)
    assert not _looks_like_question(_CHITI_BOX_NOISE)
    assert not _message_has_help_intent(_CHITI_BOX_NOISE)
