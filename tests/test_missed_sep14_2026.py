"""Регрессии по серверной очереди аналитики за 2026-09-14."""

from app.bot.heuristics import _is_missed_sep14_thread_noise
from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store


def test_sep14_real_questions_use_existing_manual_qa() -> None:
    store = load_manual_qa_store()
    for question in (
        "Корректировка стола: болты крутятся тяжело, это нормально?",
        "Почему принтер плохо печатает нависания разным пластиком?",
        "Макс расход скорости, профиль сток?",
        "Где функция заполнить стол копиями?",
        "Есть решения по поводу кривизны стола?",
    ):
        assert find_manual_qa_answer(store, question) is not None


def test_sep14_thread_noise_is_filtered() -> None:
    for message in (
        "Как и мне пластик этот и все",
        "хз как там у чела 0.068 получилось",
        "Тебе китаец выслал пластики? Меня игнорит",
        "нууууу, а как же научиться стол крутить)",
        "я к тому, что за вкусную цену продают петг кингрун, а он весь скоростной",
        "Прикол как оказалось одна была бракованная. Мы ее тестили она изображение не выдавала. А она никогда монитора то не видела",
    ):
        assert _is_missed_sep14_thread_noise(message)


def test_sep14_filter_keeps_real_diagnostics() -> None:
    for message in (
        "Почему у меня плохо печатает нависания на Kobra S1?",
        "Как выровнять стол, если он кривой?",
        "Почему Kobra S1 не печатает и выдаёт ошибку 11518?",
        "Как настроить печать PETG на высокой скорости?",
    ):
        assert not _is_missed_sep14_thread_noise(message)
