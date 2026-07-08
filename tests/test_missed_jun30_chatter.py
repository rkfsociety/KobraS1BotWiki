"""Регрессии по разбору missed_questions 2026-06-30."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_non_wiki_chatter_message,
    _is_offtopic_work_life_sidebar,
)


def test_multicolor_pause_overnight_manual_qa():
    entries = load_manual_qa_store()
    msg = (
        "Сейчас печатал многоцвет петг и закончился один цвет. Будет только завтра. "
        "Как максимально сохранить печать?"
    )
    assert find_manual_qa_answer(entries, msg)


def test_retraction_manual_qa():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "я чайник и не понимаю что такое откаты")


def test_anycubic_profile_manual_qa():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "тут везде для бамбулаб. А как найти для аникубика?")


def test_print_hours_manual_qa():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "где у Кобры S1 наработку смотреть")
    assert find_manual_qa_answer(entries, "Ну через ВПН подключил но чёт там 47 часов показывает")


def test_money_spam_is_chatter():
    assert _is_non_wiki_chatter_message("НУЖНЫ БАБКИ ?? ПИШИ МНЕ")


def test_long_anecdote_is_chatter():
    snippet = "В проектный институт спустили сверху разнарядку провести сокращение штата"
    assert _is_conversational_chatter(snippet + " " + "ЖОРы" * 20)


def test_ssh_community_poll_is_chatter():
    msg = "есть у кого-то ssh сервер для 2.7.2.7? чот у меня старый не работает"
    assert _is_non_wiki_chatter_message(msg)


def test_welding_factory_chat_is_chatter():
    msg = "У меня кореш учился на сварщика и там препод говорил про аргон"
    assert _is_offtopic_work_life_sidebar(msg)
    assert _is_conversational_chatter(msg)


def test_retraction_opinion_is_chatter():
    msg = "А вообще зачем трогать ретракты ? Они в стоке норм стоят"
    assert _is_non_wiki_chatter_message(msg)


def test_fragment_clog_is_chatter():
    assert _is_non_wiki_chatter_message("если чуть забито то из-за этого может быть?")


def test_real_retraction_help_not_chatter():
    assert not _is_non_wiki_chatter_message("как настроить откаты на kobra s1?")
    assert not _is_non_wiki_chatter_message("подскажите что такое откаты в слайсере")
