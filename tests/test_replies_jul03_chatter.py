"""Регрессии по разбору recent_replies 2026-07-03."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_ace_meta_banter,
    _is_conversational_chatter,
    _is_non_wiki_chatter_message,
    _is_personal_upholstery_project_sidebar,
    _is_thread_continuation_filler,
)


def test_softer_tpu_shore_manual_qa():
    msg = (
        "Тпу, по крайней мере 95а нифига мягкой не будет при комнатной температуре, "
        "а что б более мягкий на с1 печатать еще те танцы должны быть"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_handle_modeling_manual_qa():
    msg = (
        "Пожалуйста подскажите, как можно смоделить такую ручку максимально точно, "
        "неровностей и скруглений куча, хочу ей сделать чехолчик из тпу"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_load_ok_print_fail_manual_qa():
    msg = (
        "На принудительной подаче подача есть, а при печати нет. "
        "Я не печатаю пла и не знаю на скок он греет при подаче, так ж как у всех 250?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_heat_creep_on_print_start_manual_qa():
    msg = (
        "Если прогонять пластик до печати то он идеально идёт. Новое сопло поставил. "
        "Но как только ставишь на печать деталь происходит какой то баг при подготовки печати "
        "и вылетает ошибка забивается он в радиаторе"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_filament_cutter_manual_qa():
    msg = "Парни подскажите что делать? Грешу на нож который режет филамент он походу не срабатывает"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace_meta_banter_is_chatter():
    msg = "Что вы там на аську жалуетесь 😂"
    assert _is_ace_meta_banter(msg)
    assert _is_conversational_chatter(msg)


def test_chair_upholstery_sidebar_is_chatter():
    msg = (
        "Ткань как то не охото, учитывая что это мягкий пластик и с ним комфортно, "
        "а тут как раз и кресло обновить и руку набить по возможности"
    )
    assert _is_personal_upholstery_project_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_print_timing_continuation_is_chatter():
    msg = "это ж во время печатати прям или как?"
    assert _is_thread_continuation_filler(msg)
    assert _is_conversational_chatter(msg)


def test_real_cutter_question_not_chatter():
    assert not _is_ace_meta_banter(
        "Нож режет филамент не срабатывает, что делать на kobra s1?"
    )


def test_real_tpu_modeling_not_sidebar():
    assert not _is_personal_upholstery_project_sidebar(
        "Подскажите как смоделить ручку под чехол из тпу?"
    )
