"""Регрессии по разбору missed_questions 2026-07-03."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_community_experience_poll,
    _is_conversational_chatter,
    _is_klipper_offtopic_sidebar,
    _is_non_wiki_chatter_message,
    _is_offtopic_gas_station_joke,
    _is_vague_fix_without_symptom,
)


def test_nozzle_key_manual_qa():
    assert find_manual_qa_answer(load_manual_qa_store(), "Какой ключ нужен для сопла s1?")


def test_thermistor_manual_qa():
    msg = (
        "Хорошо, допустим понижу температуру и ничего не изменится "
        "то в чем может быть проблема, термодатчик не мог умереть?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_petg_bed_50_manual_qa():
    assert find_manual_qa_answer(load_manual_qa_store(), "Всм 50 градусов на петг?")


def test_print_speeds_manual_qa():
    msg = "всем привет А кто на каких скоростях печатает на кубике?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_firmware_download_manual_qa():
    msg = "у меня не было такой.была какая то 2.5дальше не помню цифры.есть где скачать 2.6.0.0?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_thanks_meta_is_chatter():
    msg = "спасибо, что обяснил, а то все перелазил и не нашел ясного ответа, почему оно так делало"
    assert _is_conversational_chatter(msg)


def test_klipper_btt_sidebar_is_chatter():
    msg = (
        "Бтт какая плата? У них свои сборки оси с клиппером, у распбери свои, "
        "у мелков вообще ось перелопачена, у орандж пи тоже свои особенности"
    )
    assert _is_klipper_offtopic_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_klipper_host_question_is_chatter():
    msg = "Хост один на два принтера? Возможно прошивки на том, где работает, не конфликтуют с версией клиппера"
    assert _is_klipper_offtopic_sidebar(msg)


def test_gas_station_joke_is_chatter():
    msg = "В фильтрах выбираешь 95, далее жмешь слева вверху азс и выбирает только заправки где есть бензин"
    assert _is_offtopic_gas_station_joke(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_vague_fix_without_symptom():
    assert _is_vague_fix_without_symptom("Подскажите как это исправить?")


def test_speed_poll_is_chatter():
    msg = "А есть тут шаришие в клипере?"
    assert _is_community_experience_poll(msg)


def test_real_nozzle_key_not_klipper():
    assert not _is_klipper_offtopic_sidebar("Какой ключ нужен для сопла s1?")


def test_real_thermistor_not_gas_joke():
    assert not _is_offtopic_gas_station_joke(
        "термодатчик не мог умереть при печати petg?"
    )
