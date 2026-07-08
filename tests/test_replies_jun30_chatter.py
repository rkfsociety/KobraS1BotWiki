"""Регрессии по разбору recent_replies 2026-06-30."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_figurative_mood_remark,
    _is_non_wiki_chatter_message,
)


def test_ace_s1_compatibility_manual_qa():
    entries = load_manual_qa_store()
    msg = (
        "хочу купить Kobra 3 V2 Combo ради бокса амс. "
        "Подскажите амс-ка же без проблем должна завестись с s1?"
    )
    assert find_manual_qa_answer(entries, msg)


def test_silk_pla_manual_qa():
    entries = load_manual_qa_store()
    msg = "Впервые взял силк пластик, какие советы к его печати?"
    assert find_manual_qa_answer(entries, msg)


def test_grabli_mood_is_chatter():
    msg = "Такое чувство что перед граблями очередь стоит…"
    assert _is_figurative_mood_remark(msg)
    assert _is_conversational_chatter(msg)


def test_cheap_hobby_opinion_is_chatter():
    msg = "Такое ощущение что кто то где то сказал что 3д печать это капец как дешевое хобби"
    assert _is_figurative_mood_remark(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_real_silk_question_not_chatter():
    assert not _is_figurative_mood_remark(
        "Впервые взял силк пластик, какие советы к его печати?"
    )


def test_real_ace_question_not_chatter():
    assert not _is_figurative_mood_remark(
        "Подскажите ace pro заведётся на kobra s1?"
    )
