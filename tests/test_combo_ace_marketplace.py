"""AliExpress/цена: «комбо с какой аськой» — не ace-pro-filament-replacement."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_combo_ace_marketplace_chat,
    _topic_is_marketplace_commerce_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable

_QUESTION = "На алике Х комбо стоит щас 40₽ · комбо это с какой аськой?"

_BAD_URL = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/"
    "ace-pro-filament-replacement-guide"
)


def test_combo_ace_marketplace_chat_detected():
    assert _is_combo_ace_marketplace_chat(_QUESTION)
    assert _topic_is_marketplace_commerce_intent(_QUESTION)


def test_filament_replacement_rejected():
    assert not _response_wiki_url_acceptable(_QUESTION, _BAD_URL)
