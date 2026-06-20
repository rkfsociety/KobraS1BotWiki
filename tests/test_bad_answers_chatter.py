"""Регрессии по ошибочным ответам из data/bad_answers.json.

Все эти реплики бот раньше принимал за вопросы и отвечал ссылкой из вики.
Теперь они должны распознаваться как болтовня и не получать ответа.
"""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_bare_combo_variant_fragment,
    _is_competitor_model_disambiguation,
    _is_content_post_request,
    _is_conversational_chatter,
    _is_marketplace_search_chatter,
    _is_multicolor_tower_rhetoric,
    _is_non_wiki_chatter_message,
    _is_peer_diagnostic_checklist,
    _is_profanity_outburst_chatter,
    _is_social_location_question,
    _is_thread_continuation_filler,
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


# --- вторая партия ошибочных ответов ---

def test_peer_diagnostic_checklist_is_chatter():
    assert _is_peer_diagnostic_checklist("Боковой вентилятор работает?")
    assert _is_peer_diagnostic_checklist("Температура, фирма пластика, хотенд?")
    assert _is_conversational_chatter("Боковой вентилятор работает?")
    assert _is_conversational_chatter("Температура, фирма пластика, хотенд?")


def test_bare_combo_fragment_is_chatter():
    assert _is_bare_combo_variant_fragment("Комбо?")
    assert _is_bare_combo_variant_fragment("гарантийный комбо?")
    assert _is_conversational_chatter("Комбо?")
    assert _is_conversational_chatter("гарантийный комбо?")


def test_social_location_question_is_chatter():
    assert _is_social_location_question("Вы территориально откуда?")
    assert _is_conversational_chatter("Вы территориально откуда?")


def test_content_post_request_is_chatter():
    assert _is_content_post_request("Видео нарезки будет?")
    assert _is_conversational_chatter("Видео нарезки будет?")


def test_thread_continuation_filler_is_chatter():
    assert _is_thread_continuation_filler("хотя ладно, не везде. Но есть профиля где выключен")
    assert _is_thread_continuation_filler("это я понял, но делайте как я вам надиктовал))")


def test_competitor_disambiguation_is_chatter():
    assert _is_competitor_model_disambiguation("а хот к2 это чё, кобра 2? или креалити к2")
    assert _is_conversational_chatter("а хот к2 это чё, кобра 2? или креалити к2 😁")


def test_long_profanity_rant_without_question_is_chatter():
    assert _is_profanity_outburst_chatter(
        "Я вчера до всех роликов доебался там всё как в аптеке. С завода блять так не выставлено"
    )


# --- реальные вопросы из второй партии не должны блокироваться ---

def test_real_fan_problem_not_diagnostic_checklist():
    assert not _is_peer_diagnostic_checklist("почему вентилятор не работает на kobra s1?")
    assert not _is_peer_diagnostic_checklist("у меня не работает боковой вентилятор, что делать?")


def test_real_video_help_not_content_request():
    assert not _is_content_post_request("видео как калибровать стол есть?")


def test_real_temperature_question_not_chatter():
    assert not _is_conversational_chatter("какую температуру стола ставить для петг?")
