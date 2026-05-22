"""Настройки слайсера под PETG/TPU: без уточнения модели принтера."""
from __future__ import annotations

from app.bot.layer_model_gate import (
    needs_model_clarification_for,
    topic_is_layer_slicing_intent,
    topic_requires_printer_model,
)
from app.bot.text_heuristics import (
    _needs_model_clarification,
    _topic_is_filament_slicing_settings_intent,
    _topic_needs_printer_model,
)
from app.bot.wiki_ranking import (
    _filament_material_guide_url_plausible,
    _response_wiki_url_acceptable,
)

_BRIDGE_MSG = (
    "первый слой после связующего слоя поддержки в нарезке идет как мост, "
    "если повысить поток моста, то линии спекутся друг с другом лучше · "
    "но это работает с петг, с тпу пока не пробовал"
)

_FILAMENT_RESIN = "https://wiki.anycubic.com/en/filament-and-resin"
_KOBRA2_OVERVIEW = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-2"


def test_bridge_petg_slicing_intent_detected():
    assert _topic_is_filament_slicing_settings_intent(_BRIDGE_MSG)


def test_bridge_petg_no_model_clarify():
    assert not _topic_needs_printer_model(_BRIDGE_MSG)
    assert not _needs_model_clarification(_BRIDGE_MSG)
    assert not needs_model_clarification_for(_BRIDGE_MSG)
    assert not topic_requires_printer_model(_BRIDGE_MSG)


def test_bridge_petg_layer_keyword_not_printer_specific():
    assert not topic_is_layer_slicing_intent(_BRIDGE_MSG)


def test_filament_resin_url_acceptable():
    assert _filament_material_guide_url_plausible(_FILAMENT_RESIN)
    assert _response_wiki_url_acceptable(_BRIDGE_MSG, _FILAMENT_RESIN)


def test_kobra_overview_rejected_for_bridge_petg():
    assert not _response_wiki_url_acceptable(_BRIDGE_MSG, _KOBRA2_OVERVIEW)
