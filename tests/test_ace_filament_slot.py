"""ACE Pro: слот запомнил PETG по чипу — без clarify принтера."""
from __future__ import annotations

import app.bot.layer_model_gate as g

g.apply_runtime_patches()

from app.bot.layer_model_gate import needs_model_clarification_for, response_wiki_url_acceptable
from app.bot.text_heuristics import (
    _needs_model_clarification,
    _topic_is_ace_filament_slot_intent,
    _topic_needs_printer_model,
)
from app.printer_catalog import explain_ace_filament_slot_reset

_QUESTION = (
    "Вопрос такой, ace pro запомнил petg на 1 слоте и не даёт его сменить. "
    "Дело в том что стоял аникубиковская катушка с чипом и он её запомнил "
    "и теперь сбросить не могу. Подскажете люди добрые как сбросить эти настройки?"
)

_GOOD_URL = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/"
    "ace-pro-filament-replacement-guide"
)


def test_ace_slot_intent_detected():
    assert _topic_is_ace_filament_slot_intent(_QUESTION)


def test_no_printer_model_clarify():
    assert not _topic_needs_printer_model(_QUESTION)
    assert not _needs_model_clarification(_QUESTION)
    assert not needs_model_clarification_for(_QUESTION)


def test_filament_replacement_url_acceptable():
    assert response_wiki_url_acceptable(_QUESTION, _GOOD_URL)


def test_design_reply_present():
    expl = explain_ace_filament_slot_reset(_QUESTION)
    assert expl
    assert "rfid" in expl.lower() or "чип" in expl.lower()
