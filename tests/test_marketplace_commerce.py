"""WB/Ozon, ТН ВЭД — не путать с гайдом по филаменту."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_non_wiki_chatter_message,
    _topic_is_filament_material_choice_intent,
    _topic_is_marketplace_commerce_intent,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable
from app.ru_layer import expand_queries
from app.web_wiki_index import _looks_like_question

_WB_TNVED = (
    "Вопрос, на WB есть кто продаёт? Модели напечатанные из пластика. "
    "Какой тн вэд указывать? Ни один не подходит."
)

_FILAMENT_GUIDE = "https://wiki.anycubic.com/en/filament-and-resin/filament-guide"


def test_marketplace_commerce_intent_detected():
    assert _topic_is_marketplace_commerce_intent(_WB_TNVED)


def test_not_filament_material_choice():
    assert not _topic_is_filament_material_choice_intent(_WB_TNVED)


def test_commerce_is_non_wiki_chatter():
    assert _is_non_wiki_chatter_message(_WB_TNVED)
    assert _is_conversational_chatter(_WB_TNVED)
    assert not _looks_like_question(_WB_TNVED)


def test_filament_guide_rejected_for_commerce():
    assert not _response_wiki_url_acceptable(_WB_TNVED, _FILAMENT_GUIDE)


def test_expand_skips_plastic_to_filament_for_commerce():
    variants = expand_queries(_WB_TNVED)
    assert not any("filament plastic material" in v for v in variants)
