"""Не отвечать на рекламные ссылки маркетплейсов."""
from __future__ import annotations

from app.bot.text_heuristics import _is_marketplace_promo_message
from app.web_wiki_index import _looks_like_question

_ALI_MSG = (
    "Смотри, что есть на AliExpress! ANYCUBIC Kobra 2 Max 3D-принтер за 36 521 ₽ "
    "- уже со скидкой 20%\nhttps://ali.click/1b7va15"
)


def test_marketplace_promo_detected():
    assert _is_marketplace_promo_message(_ALI_MSG)


def test_marketplace_promo_not_a_question():
    assert not _looks_like_question(_ALI_MSG)


def test_real_question_still_detected():
    q = "что делать если kobra s1 не подаёт филамент?"
    assert not _is_marketplace_promo_message(q)
    assert _looks_like_question(q)
