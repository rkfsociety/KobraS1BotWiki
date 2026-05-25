"""Отрыв TPU со стола: design-ответ, не print-tpu чужой модели."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _topic_is_filament_bed_removal_intent,
    _topic_is_filament_material_choice_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable
from app.printer_catalog import explain_filament_bed_removal

_QUESTION = "А есть какие нибудь советы как проще всего тпу от пластины отрывать?"

_WRONG_URL = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/print-tpu"
)


def test_bed_removal_intent_detected():
    assert _topic_is_filament_bed_removal_intent(_QUESTION)


def test_not_material_choice_due_to_kakie_sovety():
    assert not _topic_is_filament_material_choice_intent(_QUESTION)


def test_wrong_print_tpu_rejected_without_model():
    assert not _response_wiki_url_acceptable(_QUESTION, _WRONG_URL)


def test_design_reply_present():
    expl = explain_filament_bed_removal(_QUESTION)
    assert expl
    assert "осты" in expl.lower() or "шпател" in expl.lower()
