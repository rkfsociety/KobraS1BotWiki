"""Регрессии по разбору missed_questions 2026-07-21."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_homing_endstop_thread_sidebar,
    _is_missed_jul21_thread_noise,
    _is_non_wiki_chatter_message,
    _is_vpn_bot_spam,
)


def test_homing_manual_qa():
    msg = (
        "Но я не знаю как он определяет крайнее положение по оси . "
        "Программно ли, датчиком в голове"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_brush_mount_manual_qa():
    msg = "А какое крепление у с1 для щётки/валика штатное? Мб от мах подойдёт?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_firmware_reboot_manual_qa():
    assert find_manual_qa_answer(load_manual_qa_store(), "когда скачиваю он презагружается")


def test_wiki_vpn_manual_qa():
    msg = "Вики эникубовское чет даже через КВН у меня не открывает у всех так?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_fan_types_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "это aux fan или chamber fan? или вент модели?"
    )


def test_belt_tension_manual_qa():
    msg = (
        "Добрый! А это сильно плохо? Ремни на XY я по мануалу потянул. "
        "Первая картинка до, вторая после подтяжки. Ничего не поменялось"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_chamber_connector_manual_qa():
    assert find_manual_qa_answer(
        load_manual_qa_store(), "А для чего разъем в камере ? Или это для лазера ?"
    )


def test_vpn_spam_is_chatter():
    msg = "Ребят, кто здесь спрашивал про норм впн? ищите в телеграме lotvpnbot, проверено."
    assert _is_vpn_bot_spam(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_homing_sidebar_is_chatter():
    assert _is_homing_endstop_thread_sidebar("У меня когда без крышки запускал он тупо в угол долбился")
    assert _is_conversational_chatter("На ноль нажать не может?")


def test_thread_noise_is_chatter():
    assert _is_missed_jul21_thread_noise("Хотите ржаку?")
    assert _is_conversational_chatter("Гугло-ИИ пишет, что мол вообще ппц, так жить нельзя =)")


def test_real_homing_not_sidebar():
    assert not _is_homing_endstop_thread_sidebar(
        "Я просто хз как он определяет крайнее положение по оси Х"
    )


def test_real_wiki_vpn_not_spam():
    assert not _is_vpn_bot_spam(
        "Вики эникубовское чет даже через КВН у меня не открывает у всех так?"
    )
