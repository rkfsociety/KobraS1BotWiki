"""Резонанс / PA — design-ответ без clarify по чужой модели."""
from __future__ import annotations

import app.bot.layer_model_gate as g

g.apply_runtime_patches()

from app.bot.layer_model_gate import needs_model_clarification_for
from app.bot.text_heuristics import (
    _needs_model_clarification,
    _topic_is_resonance_pa_tuning_intent,
    _topic_needs_printer_model,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable
from app.printer_catalog import explain_resonance_pa_oscillations

_QUESTION = (
    "Спасибо. Пока первый слой печатает, у меня есть ещё вопрос. "
    "Вот такие затухающие колебания с чем могут быть связаны? Резонанс, pa? "
    "Автокалибровка не влияет на результат."
)

_WRONG_URL = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-2-max/"
    "kobra-2-max-layer-shift-during-printing-troubleshooting"
)


def test_resonance_pa_intent_detected():
    assert _topic_is_resonance_pa_tuning_intent(_QUESTION)


def test_no_model_clarify_for_resonance():
    assert not _topic_needs_printer_model(_QUESTION)
    assert not _needs_model_clarification(_QUESTION)
    assert not needs_model_clarification_for(_QUESTION)


def test_wrong_model_layer_shift_rejected_without_hints():
    assert not _response_wiki_url_acceptable(_QUESTION, _WRONG_URL)


def test_design_reply_present():
    expl = explain_resonance_pa_oscillations(_QUESTION)
    assert expl
    assert "резонанс" in expl.lower() or "ringing" in expl.lower()
    assert "pa" in expl.lower() or "pressure" in expl.lower()


# Болтовня-комментарий к чужому фото: голое «PA» + «?» без слов резонанса/настройки.
_PHOTO_BANTER = (
    "Кстати, тут конечно плохо видно, но прям как-будто иглой раскаленной сбоку "
    "дырочку сделали. Тоже PA шалит?"
)


def test_photo_banter_pa_not_tuning_intent():
    assert not _topic_is_resonance_pa_tuning_intent(_PHOTO_BANTER)
    assert explain_resonance_pa_oscillations(_PHOTO_BANTER) is None


def test_explicit_pa_calibration_still_intent():
    assert _topic_is_resonance_pa_tuning_intent("как откалибровать PA?")
    assert _topic_is_resonance_pa_tuning_intent("почему PA не влияет на результат?")
