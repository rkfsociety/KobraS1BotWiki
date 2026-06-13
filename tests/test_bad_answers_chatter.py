"""Регрессии по ошибочным ответам из data/bad_answers.json.

Все эти реплики бот раньше принимал за вопросы и отвечал ссылкой из вики.
Теперь они должны распознаваться как болтовня и не получать ответа.
"""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_marketplace_search_chatter,
    _is_multicolor_tower_rhetoric,
    _is_non_wiki_chatter_message,
    _is_profanity_outburst_chatter,
    _is_works_fine_reassurance,
)

# --- сами ошибочные ответы (должны стать болтовнёй) ---

def test_profanity_exclamation_is_chatter():
    assert _is_profanity_outburst_chatter("Ахуели совсем?")
    assert _is_conversational_chatter("Ахуели совсем?")


def test_profanity_rant_about_person_is_chatter():
    msg = "Как меня этот Николай заеееебааал"
    assert _is_profanity_outburst_chatter(msg)
    assert _is_conversational_chatter(msg)


def test_works_fine_reassurance_is_chatter():
    msg = "Кудва? Хз, у меня норм пашет. Но без бокса и всякого этого лгбт"
    assert _is_works_fine_reassurance(msg)
    assert _is_conversational_chatter(msg)


def test_marketplace_search_chatter_is_chatter():
    msg = "Нашел, но не то что на Авито"
    assert _is_marketplace_search_chatter(msg)
    assert _is_conversational_chatter(msg)


def test_multicolor_tower_rhetorical_question_is_chatter():
    msg = "многоцвет же без башни не чепятается ?"
    assert _is_multicolor_tower_rhetoric(msg)
    assert _is_non_wiki_chatter_message(msg)


# --- реальные вопросы не должны попадать под новые фильтры ---

def test_real_problem_with_profanity_still_answered():
    # Мат рядом с реальной темой принтера — это всё ещё проблема, не выброс эмоций.
    assert not _is_profanity_outburst_chatter("какого хуя сопло забилось на kobra s1")
    assert not _is_profanity_outburst_chatter("блин принтер не печатает, помогите")


def test_not_working_is_not_reassurance():
    assert not _is_works_fine_reassurance("у меня не работает экструдер, что делать?")
    assert not _is_works_fine_reassurance("как сделать чтобы норм печатал?")


def test_marketplace_with_help_intent_not_chatter():
    assert not _is_marketplace_search_chatter(
        "купил на авито kobra s1, как настроить стол?"
    )


def test_tower_disable_question_not_chatter():
    # «как отключить башню» — это запрос помощи, не риторика.
    assert not _is_multicolor_tower_rhetoric("как отключить башню при многоцветной печати?")
