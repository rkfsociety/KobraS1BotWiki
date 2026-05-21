"""Бытовые реплики в чате — бот не должен отвечать и не должен уточнять модель."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_generic_help_without_context,
    _message_has_help_intent,
    _needs_model_clarification,
)
from app.web_wiki_index import _looks_like_question

_BED_COMPARE_MSG = "Разберемся, тут кстати стол регулируется не сверху как на кобре"

_BED_LOOKS_BETTER_MSG = "Но выглядит лучше , чем на кобре (до того как стол крутил)"

_LINK_REQUEST = "Пасаны киньте ссыль на вики кубов по настройке стола чот лох не могу найти"

_LINK_WITH_MODEL = "киньте ссыль на вики кубов по настройке стола для kobra s1"

_REAL_QUESTION = "как откалибровать стол на kobra s1 combo?"

_THERMISTOR_OBSERVATION = "Это они термистор чтоли чисто на скотч приклеили"

_THERMISTOR_HELP = "у меня термистор отвалился на kobra s1, что делать?"


def test_bed_compare_other_printer_is_chatter():
    assert _is_conversational_chatter(_BED_COMPARE_MSG)
    assert not _looks_like_question(_BED_COMPARE_MSG)


def test_bed_looks_better_than_kobra_from_log_is_chatter():
    assert _is_conversational_chatter(_BED_LOOKS_BETTER_MSG)
    assert not _looks_like_question(_BED_LOOKS_BETTER_MSG)
    assert not _needs_model_clarification(_BED_LOOKS_BETTER_MSG)


def test_link_request_still_question_and_needs_model():
    assert not _is_conversational_chatter(_LINK_REQUEST)
    assert _looks_like_question(_LINK_REQUEST)
    assert _needs_model_clarification(_LINK_REQUEST)


def test_link_with_model_still_question_no_clarify():
    assert not _is_conversational_chatter(_LINK_WITH_MODEL)
    assert _looks_like_question(_LINK_WITH_MODEL)
    assert not _needs_model_clarification(_LINK_WITH_MODEL)


def test_comparative_kak_alone_not_help_intent():
    assert not _message_has_help_intent("стол не сверху как на кобре")


def test_real_how_to_question_has_help_intent():
    assert _message_has_help_intent(_REAL_QUESTION)
    assert _looks_like_question(_REAL_QUESTION)
    assert not _is_conversational_chatter(_REAL_QUESTION)


def test_thermistor_third_party_observation_is_chatter():
    assert _is_conversational_chatter(_THERMISTOR_OBSERVATION)
    assert not _looks_like_question(_THERMISTOR_OBSERVATION)


def test_thermistor_help_request_not_chatter():
    assert not _is_conversational_chatter(_THERMISTOR_HELP)
    assert _looks_like_question(_THERMISTOR_HELP)


def test_chtoli_does_not_trigger_what_substring():
    assert not _looks_like_question("термистор чтоли на скотч")


_CHITI_BOX_NOISE = "Но чиди бокс шумит просто ужас как 😂"


def test_chiti_box_noise_complaint_is_chatter():
    assert _is_conversational_chatter(_CHITI_BOX_NOISE)
    assert not _looks_like_question(_CHITI_BOX_NOISE)
    assert not _message_has_help_intent(_CHITI_BOX_NOISE)


_PORTAL_BELT_OBSERVATION = "Нашел тока инструкцию как портал достать и ремень снять"

_NOT_FOUND_HELP = "не могу найти инструкцию как снять ремень на kobra s1"


def test_found_only_partial_manual_is_chatter_not_question():
    assert _is_conversational_chatter(_PORTAL_BELT_OBSERVATION)
    assert not _looks_like_question(_PORTAL_BELT_OBSERVATION)
    assert not _message_has_help_intent(_PORTAL_BELT_OBSERVATION)


def test_cannot_find_manual_still_question():
    assert not _is_conversational_chatter(_NOT_FOUND_HELP)
    assert _looks_like_question(_NOT_FOUND_HELP)


_CHAT_HISTORY_REPLY = (
    'Не помню точно · ты в июне уже в чат пришел с вопросами "помогите..."😅'
    "я чат перечитал с начала, помню что где то 19го июня вроде ты впервые вопрос написал чату"
)

_BARE_HELP = "помогите!"


def test_chat_history_citing_help_is_chatter_not_generic_help():
    assert _is_conversational_chatter(_CHAT_HISTORY_REPLY)
    assert not _looks_like_question(_CHAT_HISTORY_REPLY)
    assert not _is_generic_help_without_context(_CHAT_HISTORY_REPLY)


def test_bare_help_still_generic_clarify():
    assert _is_generic_help_without_context(_BARE_HELP)


_SETTINGS_OBSERVATION = (
    "Я тут немного с настройками разбирался и заметил что сила нажатия стола "
    "это вовсе не параметр horizontal_move_z"
)

_SETTINGS_QUESTION = "какой параметр отвечает за силу нажатия стола на kobra s1?"


def test_settings_discovery_observation_is_chatter():
    assert _is_conversational_chatter(_SETTINGS_OBSERVATION)
    assert not _looks_like_question(_SETTINGS_OBSERVATION)
    assert not _needs_model_clarification(_SETTINGS_OBSERVATION)


def test_settings_parameter_question_still_question():
    assert not _is_conversational_chatter(_SETTINGS_QUESTION)
    assert _looks_like_question(_SETTINGS_QUESTION)


_BACKLASH_OPINION = (
    'Как по мне это не страшный рабочий "люфт", да есть, но не смертельно, '
    "на печать, по сути не влияет же🤔"
)


def test_backlash_opinion_is_chatter_not_question():
    assert _is_conversational_chatter(_BACKLASH_OPINION)
    assert not _looks_like_question(_BACKLASH_OPINION)
    assert not _needs_model_clarification(_BACKLASH_OPINION)


_BACKLASH_HELP = "как убрать люфт на kobra s1, подскажите"


def test_backlash_help_request_still_question():
    assert not _is_conversational_chatter(_BACKLASH_HELP)
    assert _looks_like_question(_BACKLASH_HELP)


_CUBE_SKEPTICISM = (
    "Я вообще сомневаюсь, что там кто-то будет заморачиваться, "
    "пустят на печать какой нибудь кубик и все на этом"
)


def test_cube_print_skepticism_is_chatter():
    assert _is_conversational_chatter(_CUBE_SKEPTICISM)
    assert not _looks_like_question(_CUBE_SKEPTICISM)
    assert not _needs_model_clarification(_CUBE_SKEPTICISM)


_FIRST_LAYER_START = "Ну что , первый слой запускаю 😁"

_LAYER_HELP = "первый слой кривой на kobra s1, что делать?"


def test_first_layer_announcement_is_chatter():
    assert _is_conversational_chatter(_FIRST_LAYER_START)
    assert not _looks_like_question(_FIRST_LAYER_START)
    assert not _needs_model_clarification(_FIRST_LAYER_START)


def test_first_layer_problem_still_question():
    assert not _is_conversational_chatter(_LAYER_HELP)
    assert _looks_like_question(_LAYER_HELP)


_LAYER_PROFILE_OPINION = (
    "Дык на первый слой же не повлияет , сомневаюсь что он тут будет очень сырой . "
    "На соковом профиле думаю все норм будет"
)

_LAYER_PROFILE_OPINION_NO_DOUBT = (
    "На первый слой не повлияет. На сопловом профиле думаю все норм будет"
)


def test_layer_profile_thread_opinion_from_log_is_chatter():
    assert _is_conversational_chatter(_LAYER_PROFILE_OPINION)
    assert not _looks_like_question(_LAYER_PROFILE_OPINION)
    assert not _needs_model_clarification(_LAYER_PROFILE_OPINION)


def test_layer_profile_opinion_without_skepticism_is_chatter():
    assert _is_conversational_chatter(_LAYER_PROFILE_OPINION_NO_DOUBT)
    assert not _needs_model_clarification(_LAYER_PROFILE_OPINION_NO_DOUBT)


_FIRST_DAYS_STORY = (
    "Я когда кобру взял, а пластиков еще не набрал, печатал остатками старыми. "
    "Там тоже пара таких ломких была. Короче, так я в первый же день узнал "
    "устройство головы, аськи, хаба сзади..."
)

_FILAMENT_HELP = "как заменить филамент в ace pro на kobra 3 combo?"


def test_first_days_discovery_story_is_chatter():
    assert _is_conversational_chatter(_FIRST_DAYS_STORY)
    assert not _looks_like_question(_FIRST_DAYS_STORY)
    assert not _needs_model_clarification(_FIRST_DAYS_STORY)


def test_filament_replace_question_not_chatter():
    assert not _is_conversational_chatter(_FILAMENT_HELP)
    assert _looks_like_question(_FILAMENT_HELP)


_CROOKED_BED_BANTER = (
    "Нуууу, что могу сказать 😂 · ну и вот зачем оно тебе😂"
    "спал бы спокойно и не знал про кривой стол"
)

_CROOKED_BED_HELP = "кривой стол на kobra s1, что делать?"


def test_crooked_bed_sarcasm_from_log_is_chatter():
    assert _is_conversational_chatter(_CROOKED_BED_BANTER)
    assert not _looks_like_question(_CROOKED_BED_BANTER)
    assert not _needs_model_clarification(_CROOKED_BED_BANTER)


def test_crooked_bed_help_request_still_question():
    assert not _is_conversational_chatter(_CROOKED_BED_HELP)
    assert _looks_like_question(_CROOKED_BED_HELP)


_REFUND_S1MAX_OPINION = (
    "Вот думаю если деньги вернут , то может проще X взять , по сути от s1 max толку нет, "
    "разве что только шлемы печатать 😂. А так я в основном ПЛА и петг печатал , ну и АБС чуток "
    "побаловался. Хз стал ли бы я печать композитами 🤷‍♂️, интересно конечно попробовать, "
    "но это чисто как раздавая акция , попробовал и забил 😁"
)

_PETG_CHOICE_HELP = "какой petg лучше для kobra s1?"


def test_refund_printer_material_opinion_from_log_is_chatter():
    assert _is_conversational_chatter(_REFUND_S1MAX_OPINION)
    assert not _looks_like_question(_REFUND_S1MAX_OPINION)
    assert not _needs_model_clarification(_REFUND_S1MAX_OPINION)


def test_filament_choice_question_not_chatter():
    assert not _is_conversational_chatter(_PETG_CHOICE_HELP)
