"""Ответы на clarify: болтовня и шуточные «модели» не ищут вики."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_joke_printer_model_clarify_reply,
    _is_non_wiki_chatter_message,
    _model_slug_hints,
)

_ERYONE_ORIGINAL = (
    "О качестве пластика eryone. Сломал все то что на столе в попытках "
    "добраться до нормального пластика и поставить его в ace"
)

_JOKE_MODEL = (
    "Anycubic Kobra X Max 5G GT Neo Turbo Custom 37-color "
    "with giga blaster for brain depilation"
)

_COMBINED = f"{_ERYONE_ORIGINAL} {_JOKE_MODEL}"


def test_joke_model_reply_detected():
    assert _is_joke_printer_model_clarify_reply(_JOKE_MODEL)
    assert not _model_slug_hints(_JOKE_MODEL)


def test_combined_eryone_and_joke_is_chatter():
    assert _is_non_wiki_chatter_message(_COMBINED)
    assert _is_joke_printer_model_clarify_reply(_COMBINED)


def test_real_model_not_joke():
    assert _model_slug_hints("kobra s1 combo")
    assert not _is_joke_printer_model_clarify_reply("kobra s1 combo")
