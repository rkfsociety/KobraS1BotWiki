"""Проверка: без модели принтера — уточнение, а не готовый manual_qa."""
from __future__ import annotations

from app.bot.text_heuristics import _needs_model_clarification, _topic_needs_printer_model


def test_bed_cubes_link_request_needs_model():
    text = "Пасаны киньте ссыль на вики кубов по настройке стола чот лох не могу найти"
    assert _topic_needs_printer_model(text)
    assert _needs_model_clarification(text)


def test_bed_cubes_with_kobra_no_clarify():
    text = "киньте ссыль на вики кубов по настройке стола для kobra s1"
    assert _topic_needs_printer_model(text)
    assert not _needs_model_clarification(text)
