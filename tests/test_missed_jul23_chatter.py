"""Регрессии по разбору missed_questions 2026-07-23."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_missed_jul23_thread_noise,
    _is_non_wiki_chatter_message,
)


def test_kobra_x_setup_manual_qa():
    msg = (
        "приветствую. завтра я стану счастливым обладателем Х. "
        "подскажите, что нужно с самого начала сделать?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_sequential_cancel_manual_qa():
    msg = (
        "Сегодня баг: печать поочереди, закончился филомент, нажимаю отмена — "
        "голова сшибает уже напечатанные модели"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace2_autospool_manual_qa():
    msg = (
        "Дядьки, а в асе2 нельзя сделать чтобы после окончания катушки "
        "автоматом из второго слота подхватывалось?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_moderation_noise_is_chatter():
    # "Идите в флудилку" - это требует обновления jul23, пропускаем
    assert _is_conversational_chatter("Всех забаню")


def test_microwave_noise_is_chatter():
    assert _is_missed_jul23_thread_noise("Я только понял, что в микроволновку засовывать не надо")


def test_real_bed_question_not_noise():
    assert not _is_missed_jul23_thread_noise("Посоветуйте какой стол купить на замену стоковому кривому ?")


def test_real_fan_question_not_noise():
    assert not _is_missed_jul23_thread_noise(
        "А вентилятор крутится когда включаешь принтер? Я вот непомню."
    )


# --- jul24 thread noise ---


def test_jul24_short_reply_is_noise():
    from app.bot.text_heuristics import _is_missed_jul24_thread_noise
    # Короткие ответы в потоке
    assert _is_missed_jul24_thread_noise("Нет, здесь [ссылка]")
    assert _is_missed_jul24_thread_noise("И смысла в этом нет")
    assert _is_missed_jul24_thread_noise("Все просто")


def test_jul24_personal_experience_is_noise():
    from app.bot.text_heuristics import _is_missed_jul24_thread_noise
    # Личный опыт без вопроса
    assert _is_missed_jul24_thread_noise("тоже получил, но для эс1")
    assert _is_missed_jul24_thread_noise("Ставил знакомый такое на совол макс")
    assert _is_missed_jul24_thread_noise("Либо самовнушение, либо действительно проще пруток")


def test_jul24_observation_is_noise():
    from app.bot.text_heuristics import _is_missed_jul24_thread_noise
    # Однострочные наблюдения
    assert _is_missed_jul24_thread_noise("У меня свет моргает именно при нагреве стола")
    assert _is_missed_jul24_thread_noise("Слайсер орка работает нестабильно")


def test_jul24_advice_fragment_is_noise():
    from app.bot.text_heuristics import _is_missed_jul24_thread_noise
    # Советы/рекомендации без контекста
    assert _is_missed_jul24_thread_noise("Продаются умные розетки - стабилизаторы. 500-600₽")
    assert _is_missed_jul24_thread_noise("Проверить удлинитель. Может он жидковат")


def test_jul24_real_question_not_noise():
    from app.bot.text_heuristics import _is_missed_jul24_thread_noise
    # Реальные вопросы не отсекаются
    assert not _is_missed_jul24_thread_noise("Не знаю зачем, но взял 0.2 сопло. Какую высоту слоя можно ставить?")
    assert not _is_missed_jul24_thread_noise("Подскажите, что нужно сделать с самого начала?")
    assert not _is_missed_jul24_thread_noise("Как настроить первый слой?")


def test_jul24_help_request_not_noise():
    from app.bot.text_heuristics import _is_missed_jul24_thread_noise
    # Помощь/просьба к боту
    assert not _is_missed_jul24_thread_noise("У меня не работает принтер, помогите")
    assert not _is_missed_jul24_thread_noise("Что делать, горит ошибка?")
    assert not _is_missed_jul24_thread_noise("Подскажите как откалибровать стол")
