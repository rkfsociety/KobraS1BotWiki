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


_CUBE_COMPARE_PLAN = (
    "Вот я ради интереса в понедельник попробую напечатать xyz куб "
    "и сравню с тем , что напечатала кобра"
)


def test_xyz_cube_compare_plan_is_chatter():
    assert _is_conversational_chatter(_CUBE_COMPARE_PLAN)
    assert not _looks_like_question(_CUBE_COMPARE_PLAN)
    assert not _needs_model_clarification(_CUBE_COMPARE_PLAN)


_OVERREACTION_RHETORIC = (
    'Перехвалил, вот что сейчас увидел 😂 · '
    'А я говорил про "сушить и калибровать пластик"?😂'
)


def test_overreaction_rhetoric_is_chatter():
    assert _is_conversational_chatter(_OVERREACTION_RHETORIC)
    assert not _looks_like_question(_OVERREACTION_RHETORIC)
    assert not _message_has_help_intent(_OVERREACTION_RHETORIC)
    assert not _needs_model_clarification(_OVERREACTION_RHETORIC)


_KOBRA3_STANDS_LIKE_X = "кобра 3 стоит как Х"


def test_printer_stands_like_x_is_chatter():
    assert _is_conversational_chatter(_KOBRA3_STANDS_LIKE_X)
    assert not _looks_like_question(_KOBRA3_STANDS_LIKE_X)
    assert not _needs_model_clarification(_KOBRA3_STANDS_LIKE_X)


_USED_PURCHASE_BANTER = (
    "Ну это смотря как он ее купил, как новую со скрученным пробегом, "
    "или с уценкой б/у с пробегом 35 часов · Ты говорил, что та без аськи лежала"
)


def test_used_printer_purchase_banter_is_chatter():
    assert _is_conversational_chatter(_USED_PURCHASE_BANTER)
    assert not _looks_like_question(_USED_PURCHASE_BANTER)
    assert not _needs_model_clarification(_USED_PURCHASE_BANTER)


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


_WASTE_DEBATE_RELAY = (
    "Мне тут чел в чате старпласта доказывает что меньше отходов на иксе "
    "это все маркетинг и то что режется филамент ближе к соплу это нихуя не роляет это все фикция"
)

_WASTE_FACT_QUESTION = (
    "правда ли что меньше отходов если филамент режется ближе к соплу?"
)


def test_filament_waste_debate_relay_from_log_is_chatter():
    assert _is_conversational_chatter(_WASTE_DEBATE_RELAY)
    assert not _looks_like_question(_WASTE_DEBATE_RELAY)
    assert not _needs_model_clarification(_WASTE_DEBATE_RELAY)


def test_filament_waste_fact_question_still_question():
    assert not _is_conversational_chatter(_WASTE_FACT_QUESTION)
    assert _looks_like_question(_WASTE_FACT_QUESTION)


_FILAMENT_STATS_OPINION = (
    "Я, все же, пока что, думаю, что нит не так плох, как тут раздувается. "
    "Просто ошибка статистики"
)

_FILAMENT_STATS_HELP = "ошибка 11503 на kobra s1, что делать?"


def test_filament_stats_opinion_from_log_is_chatter():
    assert _is_conversational_chatter(_FILAMENT_STATS_OPINION)
    assert not _looks_like_question(_FILAMENT_STATS_OPINION)
    assert not _needs_model_clarification(_FILAMENT_STATS_OPINION)


def test_error_code_help_not_chatter():
    assert not _is_conversational_chatter(_FILAMENT_STATS_HELP)
    assert _looks_like_question(_FILAMENT_STATS_HELP)


_ACE_PRICE_NEGOTIATION = (
    "Я предлагал ему 9 он мне говорит новая аська стоит 20 от с1 так что давай за 15"
)

_ACE_PRICE_QUESTION = "сколько стоит новая аська ace pro для kobra s1?"


def test_ace_price_negotiation_from_log_is_chatter():
    assert _is_conversational_chatter(_ACE_PRICE_NEGOTIATION)
    assert not _looks_like_question(_ACE_PRICE_NEGOTIATION)
    assert not _message_has_help_intent(_ACE_PRICE_NEGOTIATION)


def test_ace_price_question_not_chatter():
    assert not _is_conversational_chatter(_ACE_PRICE_QUESTION)
    assert _looks_like_question(_ACE_PRICE_QUESTION)


_WARHAMMER_BANTER = "Оно тебе точно не надо · А как же печать миниатюр по вахе ?😂"

_WARHAMMER_BANTER_SHORT = "А как же печать миниатюр по вахе ?😂"

_LAYER_CALIBRATION_HELP = "как настроить высоту слоя 0.16 на kobra s1 для тестовой печати?"


def test_warhammer_miniature_banter_from_log_is_chatter():
    assert _is_conversational_chatter(_WARHAMMER_BANTER)
    assert not _needs_model_clarification(_WARHAMMER_BANTER)
    assert _is_conversational_chatter(_WARHAMMER_BANTER_SHORT)
    assert not _needs_model_clarification(_WARHAMMER_BANTER_SHORT)


def test_layer_calibration_question_not_chatter():
    assert not _is_conversational_chatter(_LAYER_CALIBRATION_HELP)
    assert _looks_like_question(_LAYER_CALIBRATION_HELP)


_WARRANTY_PEER_QUESTION = "Вася у тебя кобра еще на гарантии?"

_WARRANTY_WIKI_QUESTION = "какая гарантия на kobra s1 combo?"


def test_peer_warranty_question_from_log_is_chatter():
    assert _is_conversational_chatter(_WARRANTY_PEER_QUESTION)
    assert not _needs_model_clarification(_WARRANTY_PEER_QUESTION)


def test_generic_warranty_wiki_question_not_chatter():
    assert not _is_conversational_chatter(_WARRANTY_WIKI_QUESTION)
    assert _looks_like_question(_WARRANTY_WIKI_QUESTION)
