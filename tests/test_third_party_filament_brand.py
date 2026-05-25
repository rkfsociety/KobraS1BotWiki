"""Bambu / PETG HF: design-ответ, не оглавление filament-and-resin."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_third_party_filament_brand_chat,
    _topic_is_filament_slicing_settings_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable
from app.printer_catalog import explain_third_party_filament_chat

_QUESTION = (
    "А пластик бамбулаба ведь хороший? "
    "И для petg hf надо будет более высокие скорости ставить?"
)

_HUB_URL = "https://wiki.anycubic.com/en/filament-and-resin"


def test_third_party_filament_chat_detected():
    assert _is_third_party_filament_brand_chat(_QUESTION)


def test_not_slicing_intent_for_bambu():
    assert not _topic_is_filament_slicing_settings_intent(_QUESTION)


def test_hub_url_rejected():
    assert not _response_wiki_url_acceptable(_QUESTION, _HUB_URL)


def test_design_reply_covers_bambu_and_hf():
    expl = explain_third_party_filament_chat(_QUESTION)
    assert expl
    assert "bambu" in expl.lower() or "бамбу" in expl.lower()
    assert "hf" in expl.lower() or "поток" in expl.lower()
