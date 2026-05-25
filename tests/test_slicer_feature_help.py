"""Убрать ушко в слайсере — design-ответ, не quick start."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _message_has_help_intent,
    _topic_is_slicer_feature_help_intent,
    _topic_needs_printer_model,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable
from app.printer_catalog import explain_slicer_mouse_ear_removal

_QUESTION = "Подскажите, как это ушко в слайсере убрать, никак не получается"

_QUICK_START = (
    "https://wiki.anycubic.com/en/software-and-app/new-page-anycubic-slicer-beta(orca-version)/"
    "anycubic-slicer-next-slicing-software-quick-start-guide"
)


def test_slicer_ear_intent_detected():
    assert _topic_is_slicer_feature_help_intent(_QUESTION)


def test_slicer_ear_has_help_intent():
    assert _message_has_help_intent(_QUESTION)


def test_slicer_ear_no_model_required():
    assert not _topic_needs_printer_model(_QUESTION)


def test_quick_start_rejected():
    assert not _response_wiki_url_acceptable(_QUESTION, _QUICK_START)


def test_design_reply_present():
    expl = explain_slicer_mouse_ear_removal(_QUESTION)
    assert expl
    assert "mouse ear" in expl.lower() or "ушко" in expl.lower()
