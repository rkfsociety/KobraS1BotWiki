"""Продажа ACE / TPU не из аськи — не ace-pro-notes."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_ace_unit_trade_banter,
    _is_conversational_chatter,
    _topic_is_ace_filament_drying_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable

_QUESTION = (
    "Продать? · мне Х нужен для ТПУ, печатать из аськи он не сможет, а сушить есть где"
)

_NOTES_URL = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/ace-pro-notes"

_DRYING_HELP = "как сушить petg в ace pro на kobra 3 combo?"


def test_ace_trade_banter_detected():
    assert _is_ace_unit_trade_banter(_QUESTION)
    assert _is_conversational_chatter(_QUESTION)


def test_not_drying_intent_for_trade_thread():
    assert not _topic_is_ace_filament_drying_intent(_QUESTION)


def test_ace_notes_rejected():
    assert not _response_wiki_url_acceptable(_QUESTION, _NOTES_URL)


def test_drying_help_not_trade_banter():
    assert not _is_ace_unit_trade_banter(_DRYING_HELP)
    assert _topic_is_ace_filament_drying_intent(_DRYING_HELP)
