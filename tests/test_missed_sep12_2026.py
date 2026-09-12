"""Регрессии по серверной очереди аналитики за 2026-09-12."""

from app.bot.heuristics._filter import _is_non_wiki_chatter_message
from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store


def test_sep12_real_questions_use_existing_manual_qa() -> None:
    store = load_manual_qa_store()
    for question in (
        "Тпу как вставляли загружалии? Я уже спрашивал? Не помню))",
        "Здравствуйте дайте пожалуйста ссылку на сайт чтобы создать обращение в поддержку",
        "Почему он перетыкивает точки",
    ):
        assert find_manual_qa_answer(store, question) is not None


def test_sep12_thread_noise_is_filtered() -> None:
    for message in (
        "Поэтому решил Франкенштейна собрать?",
        "Печатать многоцвет во весь стол? Дрыга из-за системы подачи пластика",
        "Кто там у них слайсер делает",
    ):
        assert _is_non_wiki_chatter_message(message)


def test_sep12_filter_does_not_hide_real_questions() -> None:
    for message in (
        "Почему он перетыкивает точки",
        "Как откалибровать стол на Kobra S1, если первый слой не липнет?",
        "После Load пластик не выходит из сопла, что проверить?",
    ):
        assert not _is_non_wiki_chatter_message(message)
