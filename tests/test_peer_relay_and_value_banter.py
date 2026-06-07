"""Болтовня: переслать видео третьему лицу, «в моих деньгах», сарказм-аналогия с машиной."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_design_feature_car_sarcasm,
    _is_money_worth_banter,
    _is_non_wiki_chatter_message,
    _is_relay_to_peer_chatter,
)

_RELAY = (
    "Скинь ему эти два видоса. Пусть поймет что такое нормальная печать. "
    "На этом принтере. Так ему и напиши - видео от администрации поддержки в рф"
)
_MONEY = "в моих деньгах это как 2 кобры с1 комбо, а в ваших и с скидками это все 3"
_CAR = "И если у него дверь в машине будет кривая - тоже особенность конструкции?"


def test_relay_to_peer_chatter():
    assert _is_relay_to_peer_chatter(_RELAY)
    assert _is_non_wiki_chatter_message(_RELAY)
    assert _is_conversational_chatter(_RELAY)


def test_money_worth_banter():
    assert _is_money_worth_banter(_MONEY)
    assert _is_non_wiki_chatter_message(_MONEY)


def test_design_feature_car_sarcasm():
    assert _is_design_feature_car_sarcasm(_CAR)
    assert _is_non_wiki_chatter_message(_CAR)


def test_real_questions_not_suppressed():
    # Настоящий вопрос про люфт двери — не сарказм-аналогия.
    assert not _is_design_feature_car_sarcasm("Дверца люфтит, это особенность конструкции или брак?")
    # «Скиньте ссылку» — обращение к боту, не пересылка третьему лицу.
    assert not _is_relay_to_peer_chatter("Скиньте ссылку на калибровку стола")
    # Просьба о помощи с упоминанием денег — не болтовня о ценности.
    assert not _is_money_worth_banter("Подскажите какую кобру купить, в моих деньгах это дорого")
