"""Регрессии по серверному snapshot очередей 13.09.2026."""

from app.bot.heuristics._filter import _is_non_wiki_chatter_message
from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store


def test_sep13_real_questions_are_covered() -> None:
    store = load_manual_qa_store()
    for question in (
        "счётчика печати не соответствует действительности",
        "Переменная это ведь не адаптивная?",
        "Защелка не пружинит как должна",
        "где таймлапсы хранятся",
        "сколько точек ставить для снятия карты",
    ):
        assert find_manual_qa_answer(store, question) is not None


def test_sep13_thread_noise_is_filtered() -> None:
    for message in (
        "По деньгам чет 1500 рассыпуха комплектом",
        "Этож томагавки",
        "Стоит перечитывать 400 сообщений?",
        "может всё таки стол ровный был? 😂",
    ):
        assert _is_non_wiki_chatter_message(message)


def test_sep13_filter_keeps_real_diagnostics() -> None:
    for message in (
        "Почему он перетыкивает точки",
        "После Load пластик не выходит из сопла",
        "Как откалибровать стол, если первый слой не липнет?",
    ):
        assert not _is_non_wiki_chatter_message(message)
