"""Регрессии по разбору missed_questions 2026-07-17."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_missed_jul17_thread_noise,
    _is_money_lend_spam,
    _is_non_wiki_chatter_message,
    _is_travel_airport_sidebar,
)


def test_clean_bed_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "Привет, чем можно отмыть пластик со стола ?"
    )


def test_first_days_manual_qa():
    msg = (
        "Первый принтер. Сравнил с аналогами этот больше заинтересовал по цене и характеристикам. "
        "С какими проблемами могу столкнуться в первые дни эксплуатации?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace_thin_filament_manual_qa():
    msg = (
        "Подаю пластик из аси, причём это единственный в аси пластик от кубиков, это ПЛА "
        "который достался мне бесплатно за предзаказ макса, и вот его подаю, а он мне в ошибку "
        "падает, и хз что делать, по вики кубиков тип малый диаметр прутка..."
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_balcony_manual_qa():
    msg = (
        "подскажите пожалуйста, поставить принтер на неотапливаемый балкон"
        "(где зимой будет холодно) - плохая идея?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_tpu_ace_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "Но известно же , что через амс пускать тпу нельзя?"
    )


def test_click_noise_manual_qa():
    msg = (
        "Подскажите, что может так щелкать при печати? Не могу понять, в чем причина. "
        "С экструдером это никак не связано. S1"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_money_spam_is_chatter():
    assert _is_money_lend_spam("Нужда в баблишке ? Обращайся.)")
    assert _is_conversational_chatter("Проблемы с бабосами? Пиши помогу")


def test_airport_sidebar_is_chatter():
    msg = (
        "Я только алипэй себе делал когда 5 часов торчал в аэропорту Китая "
        "и хотел купить пожрать в вендинге"
    )
    assert _is_travel_airport_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_thread_noise_is_chatter():
    assert _is_missed_jul17_thread_noise("Ну чо проклинашки?😁😁😁😁")
    assert _is_conversational_chatter("Как будто вмазало")


def test_real_bed_clean_not_noise():
    assert not _is_missed_jul17_thread_noise(
        "Подскажите чем отмыть пластик со стола на kobra s1"
    )


def test_real_clog_not_money():
    assert not _is_money_lend_spam(
        "Хотэнд забивается, подскажите что делать на kobra s1"
    )
