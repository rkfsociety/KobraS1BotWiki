"""Отверстия в вертикальных стенках — не quick start слайсера."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _needs_model_clarification,
    _topic_is_slicer_vertical_hole_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable
from app.printer_catalog import explain_slicer_vertical_holes

_QUESTION = (
    'Вопрос: отверстия на вертикальных стенках как то можно "починить" в слайсере? '
    "Чтоб их не сплющивало сверху · Или надо моделить само отверстие в виде капли?"
)

_QUICK_START = (
    "https://wiki.anycubic.com/en/software-and-app/new-page-anycubic-slicer-beta(orca-version)/"
    "anycubic-slicer-next-slicing-software-quick-start-guide"
)


def test_vertical_hole_intent_detected():
    assert _topic_is_slicer_vertical_hole_intent(_QUESTION)


def test_vertical_hole_no_model_clarify():
    assert not _needs_model_clarification(_QUESTION)


def test_quick_start_rejected_for_vertical_holes():
    assert not _response_wiki_url_acceptable(_QUESTION, _QUICK_START)


def test_design_reply_present():
    expl = explain_slicer_vertical_holes(_QUESTION)
    assert expl
    assert "капл" in expl.lower() or "teardrop" in expl.lower()
