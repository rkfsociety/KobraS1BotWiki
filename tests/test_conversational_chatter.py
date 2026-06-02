"""Бытовые реплики в чате — бот не должен отвечать и не должен уточнять модель."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_bare_competitor_printer_question,
    _is_competitor_showcase_request,
    _is_conversational_chatter,
    _is_conversational_skepticism,
    _is_generic_help_without_context,
    _is_hardware_vs_settings_dilemma,
    _is_non_wiki_chatter_message,
    _is_printer_purchase_material_opinion,
    _is_product_news_announcement,
    _is_technical_observation_sharing,
    _is_technical_opinion_sharing,
    _mentions_competitor_printer,
    _message_has_help_intent,
    _needs_model_clarification,
    _topic_is_marketplace_commerce_intent,
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


_NOZZLE_GUESS_DEFER = "Мое предположение , что забито сопло, но лучше подождать кого-то опытного \U0001f601"

_NOZZLE_REAL_HELP = "забито сопло на kobra s1, как почистить?"


def test_nozzle_guess_deferring_to_expert_is_chatter():
    assert _is_conversational_chatter(_NOZZLE_GUESS_DEFER)
    assert not _message_has_help_intent(_NOZZLE_GUESS_DEFER)


_HW_VS_SETTINGS_DILEMMA = (
    "голова не шатается, кривизна относительно стола имеется, шайбы в пути) "
    "принтер отпахал 250 часов и вот я его только обслужил (почистил и смазал) "
    "и решил проверить первый слой, это после того как я подкрутил винты стола "
    "на горячую, до этого было значительно лучше, но теперь все плывет, и что "
    "это действительно техничка или все таки настройки?"
)

def test_hardware_vs_settings_dilemma_no_clarify():
    assert _is_hardware_vs_settings_dilemma(_HW_VS_SETTINGS_DILEMMA)
    assert _is_non_wiki_chatter_message(_HW_VS_SETTINGS_DILEMMA)
    assert not _needs_model_clarification(_HW_VS_SETTINGS_DILEMMA)


_PROBLEM_COMBO = "+ кривая тенза/незатянутая тенза и т.д. вместе с плавающим столом ядреная смесь"


def test_problem_combo_banter_is_chatter():
    assert _is_conversational_chatter(_PROBLEM_COMBO)
    assert _is_non_wiki_chatter_message(_PROBLEM_COMBO)


def test_tension_help_request_not_chatter():
    assert not _is_conversational_chatter("ремень незатянут, как настроить натяжение?")


_COMBO_DELIBERATION = "Да я как-то думал про комбо версию . Но послушав Васю уже не уверен 😂😂😂😂"


def test_combo_purchase_deliberation_is_chatter():
    assert _is_conversational_chatter(_COMBO_DELIBERATION)
    assert _is_non_wiki_chatter_message(_COMBO_DELIBERATION)
    assert not _needs_model_clarification(_COMBO_DELIBERATION)


def test_combo_assembly_howto_not_chatter():
    # Реальный запрос по сборке комбо-версии — не болтовня.
    assert not _is_non_wiki_chatter_message("как собрать комбо версию kobra s1?")


def test_hardware_vs_settings_with_how_to_not_dilemma():
    # Явная просьба «как настроить» оставляет сообщение запросом помощи.
    assert not _is_hardware_vs_settings_dilemma(
        "это техничка или настройки, как настроить первый слой?"
    )


def test_nozzle_real_help_still_answered():
    assert not _is_conversational_chatter(_NOZZLE_REAL_HELP)
    assert _looks_like_question(_NOZZLE_REAL_HELP)


_PEER_TEMP_INTERROGATION = "Забито сопло. Температура какая была?"

_TEMP_WIKI_QUESTION = "какая температура сопла нужна для PETG на kobra s1?"


def test_peer_temperature_interrogation_is_chatter():
    assert _is_conversational_chatter(_PEER_TEMP_INTERROGATION)


def test_temp_setting_question_still_answered():
    assert not _is_conversational_chatter(_TEMP_WIKI_QUESTION)
    assert _looks_like_question(_TEMP_WIKI_QUESTION)


_FEED_PROBE = "Если дать с принтера подачу филамента с сопла пластик идет равномерно и ровно?"

_FEED_REAL_HELP = "как настроить подачу филамента на kobra s1?"


def test_filament_feed_probe_is_chatter():
    assert _is_conversational_chatter(_FEED_PROBE)


def test_filament_feed_setup_question_still_answered():
    assert not _is_conversational_chatter(_FEED_REAL_HELP)
    assert _looks_like_question(_FEED_REAL_HELP)


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


_TPU_STRENGTH_DISCUSSION = (
    "Мне интересно, будет ли он прочнее при печати под углом, сломаться то послойно ему сложнее будет · "
    "Tpu, как я понял, при нормальном спекании пофиг, по слоям, или поперёк."
)


def test_tpu_strength_discussion_is_chatter():
    from app.bot.layer_model_gate import needs_model_clarification_for, topic_is_layer_slicing_intent

    assert _is_conversational_chatter(_TPU_STRENGTH_DISCUSSION)
    assert not topic_is_layer_slicing_intent(_TPU_STRENGTH_DISCUSSION)
    assert not needs_model_clarification_for(_TPU_STRENGTH_DISCUSSION)
    assert not _looks_like_question(_TPU_STRENGTH_DISCUSSION)


_PRINT_QUALITY_CURIOSITY = (
    "Вот давно возникает вопрос, а как они так печатают, что даже и не похоже на то , "
    "что это 3д печать? Или это просто на видео кажется"
)


def test_print_quality_video_curiosity_is_chatter():
    assert _is_conversational_chatter(_PRINT_QUALITY_CURIOSITY)
    assert not _looks_like_question(_PRINT_QUALITY_CURIOSITY)
    assert not _message_has_help_intent(_PRINT_QUALITY_CURIOSITY)


_KOBRA_X_FRAGMENT = "Как кобра х"


def test_colloquial_kobra_fragment_is_chatter():
    assert _is_conversational_chatter(_KOBRA_X_FRAGMENT)
    assert not _looks_like_question(_KOBRA_X_FRAGMENT)
    assert not _message_has_help_intent(_KOBRA_X_FRAGMENT)


_CHITU_CHAT_TIP = (
    "О, в чате по чиди увиле инфу, что фунссор и на чиди q2 делает стол 😁"
)


def test_cross_chat_chitu_tip_is_chatter():
    import app.bot.layer_model_gate as g

    g.apply_runtime_patches()
    from app.bot.layer_model_gate import needs_model_clarification_for

    assert _is_conversational_chatter(_CHITU_CHAT_TIP)
    assert not needs_model_clarification_for(_CHITU_CHAT_TIP)
    assert not _looks_like_question(_CHITU_CHAT_TIP)


_TWO_ACE_BANTER = "а говорит многоцвет не печатает, вот зачем ему две аськи?"


def test_multicolor_ace_sarcasm_is_chatter():
    import app.bot.layer_model_gate as g

    g.apply_runtime_patches()
    from app.bot.layer_model_gate import needs_model_clarification_for

    assert _is_conversational_chatter(_TWO_ACE_BANTER)
    assert not needs_model_clarification_for(_TWO_ACE_BANTER)
    assert not _looks_like_question(_TWO_ACE_BANTER)
    assert not _message_has_help_intent(_TWO_ACE_BANTER)


_CHITU_ACE_MOTORS = "а в чиди боксе на каждую катушку по движку. Как я понял и в аська 2 тоже"


def test_chitu_ace_motor_observation_is_chatter():
    assert _is_conversational_chatter(_CHITU_ACE_MOTORS)
    assert not _looks_like_question(_CHITU_ACE_MOTORS)
    assert not _message_has_help_intent(_CHITU_ACE_MOTORS)


_MULTICOLOR_BANTER = "Сэамэйкер 95700 · Кто то наигрался с быстрым многоцветом😂"


def test_multicolor_preset_banter_is_chatter():
    assert _is_conversational_chatter(_MULTICOLOR_BANTER)
    assert not _looks_like_question(_MULTICOLOR_BANTER)
    assert not _message_has_help_intent(_MULTICOLOR_BANTER)


_BAMBU_EXTRUDER_STORY = (
    "А вот это другое дело · Мне когда первый раз пришлось экструдер разбирать на п2с, "
    "я сначала нажрался, а потом разобрал. на трезвую голову рука не поднялась разбирать бамбук"
)


_P2S_ESUN_OOZE = (
    "Я его купил только потому что п2с есун не хотел печатать, был брак... "
    "А техподдержка нафиг шлет, все проверки и калибровки только с оригой пластиком, "
    "вот и пришлось купить оригу · Но он и оригу печатает так же как и есун, "
    "сильно течет, собирает каплю и портит печать потом"
)

_EXTRA_MATERIAL_URL = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/common/kobra-series-extra-material-in-printing"
)


def test_p2s_esun_ooze_story_from_log_is_chatter():
    assert _is_conversational_chatter(_P2S_ESUN_OOZE)
    assert not _needs_model_clarification(_P2S_ESUN_OOZE)


def test_other_printer_extruder_story_is_chatter():
    import app.bot.layer_model_gate as g

    g.apply_runtime_patches()
    from app.bot.layer_model_gate import needs_model_clarification_for

    assert _is_conversational_chatter(_BAMBU_EXTRUDER_STORY)
    assert not needs_model_clarification_for(_BAMBU_EXTRUDER_STORY)
    assert not _looks_like_question(_BAMBU_EXTRUDER_STORY)


_ORCA_OPINION = "А зачем для кобры орка? Стандартный слайсер огонь"


def test_orca_vs_slicer_opinion_is_chatter():
    assert _is_conversational_chatter(_ORCA_OPINION)
    assert not _looks_like_question(_ORCA_OPINION)
    assert not _message_has_help_intent(_ORCA_OPINION)


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


_ACE_PRICE_HYPERBOLE = "А отдельно аська новая наверное как крыло от самолета будет стоить 😁"

_ACE_PRICE_REAL_QUESTION = "сколько стоит новая аська ace pro для kobra s1?"


def test_ace_price_hyperbole_from_log_is_chatter():
    assert _is_conversational_chatter(_ACE_PRICE_HYPERBOLE)
    assert not _looks_like_question(_ACE_PRICE_HYPERBOLE)
    assert not _message_has_help_intent(_ACE_PRICE_HYPERBOLE)
    assert not _needs_model_clarification(_ACE_PRICE_HYPERBOLE)


def test_ace_price_real_question_not_hyperbole():
    assert not _is_conversational_chatter(_ACE_PRICE_REAL_QUESTION)
    assert _looks_like_question(_ACE_PRICE_REAL_QUESTION)


_CHAT_INCIDENT_RECOLLECTION = (
    "тут же было в чате как то, кобра глюка словила, когда в подстанцую машина врезалась и свет отрубили"
)

_POWER_OUTAGE_HELP = "кобра выключилась при отключении света, как восстановить печать на kobra s1?"


def test_chat_past_incident_recollection_is_chatter():
    assert _is_conversational_chatter(_CHAT_INCIDENT_RECOLLECTION)
    assert not _looks_like_question(_CHAT_INCIDENT_RECOLLECTION)
    assert not _message_has_help_intent(_CHAT_INCIDENT_RECOLLECTION)
    assert not _needs_model_clarification(_CHAT_INCIDENT_RECOLLECTION)


def test_power_outage_recovery_help_still_question():
    assert not _is_conversational_chatter(_POWER_OUTAGE_HELP)
    assert _looks_like_question(_POWER_OUTAGE_HELP)


_ERYONE_QUALITY_OPINION = (
    "О качестве пластика eryone. Сломал все то что на столе в попытках "
    "добраться до нормального пластика и поставить его в ace"
)

_ERYONE_QUALITY_HELP = "какой eryone petg лучше взять для kobra s1?"


def test_eryone_quality_opinion_from_log_is_chatter():
    assert _is_conversational_chatter(_ERYONE_QUALITY_OPINION)
    assert not _looks_like_question(_ERYONE_QUALITY_OPINION)
    assert not _needs_model_clarification(_ERYONE_QUALITY_OPINION)


def test_eryone_brand_choice_question_not_chatter():
    assert not _is_conversational_chatter(_ERYONE_QUALITY_HELP)
    assert _looks_like_question(_ERYONE_QUALITY_HELP)


_TOLERANCE_BANTER = (
    "Так как одному богу известно какой там зазор между пластиком и втулкой получается"
)

_FILAMENT_CHOICE_HELP = "какой petg лучше взять для kobra s1?"


def test_filament_tolerance_banter_from_log_is_chatter():
    assert _is_conversational_chatter(_TOLERANCE_BANTER)
    assert not _looks_like_question(_TOLERANCE_BANTER)
    assert not _needs_model_clarification(_TOLERANCE_BANTER)


def test_filament_choice_question_not_tolerance_banter():
    assert not _is_conversational_chatter(_FILAMENT_CHOICE_HELP)
    assert _looks_like_question(_FILAMENT_CHOICE_HELP)


_ALI_COMBO_ACE = "На алике Х комбо стоит щас 40₽ · комбо это с какой аськой?"

_ACE_REPLACE_HELP = "как заменить филамент в ace pro на kobra 3 combo?"


def test_ali_combo_ace_price_from_log_is_chatter():
    assert _is_conversational_chatter(_ALI_COMBO_ACE)
    assert not _looks_like_question(_ALI_COMBO_ACE)


def test_ace_filament_replace_help_not_marketplace_chat():
    assert not _is_conversational_chatter(_ACE_REPLACE_HELP)
    assert _looks_like_question(_ACE_REPLACE_HELP)


def test_ace_unit_price_banter_from_log_is_chatter():
    assert _is_conversational_chatter("10₽ вторая аська? Дорого?₽")


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


# --- Bare competitor printer question (log 07:55:31): «А1 комбо?» ---

def test_bambu_a1_combo_question_from_log_is_chatter():
    assert _is_bare_competitor_printer_question("А1 комбо?")
    assert _is_conversational_chatter("А1 комбо?")
    assert not _needs_model_clarification("А1 комбо?")


def test_bare_competitor_variations_are_chatter():
    assert _is_bare_competitor_printer_question("a1 combo?")
    assert _is_bare_competitor_printer_question("bambu?")
    assert _is_bare_competitor_printer_question("p2s?")


def test_long_competitor_question_not_caught():
    # Длинный вопрос с конкурентом — не отсекаем, бот может дать ответ
    assert not _is_bare_competitor_printer_question(
        "как настроить ретракт на bambu a1 combo?"
    )


# --- Лог 07:59:33: шутка о тайминге покупки ---

_COMBO_TIMING_JOKE = "А то будет как обычно, куплю Х, а на следующий день комбо выйдет😂"


def test_purchase_timing_joke_from_log_is_chatter():
    assert _is_printer_purchase_material_opinion(_COMBO_TIMING_JOKE)
    assert _is_conversational_chatter(_COMBO_TIMING_JOKE)
    assert not _needs_model_clarification(_COMBO_TIMING_JOKE)


# --- Лог 08:02:40: совет по комплектации заказа ---

_ORDER_ADVICE_MSG = (
    "Что ещё сразу докинуть к заказу кроме филамента? "
    "Не имею ни малейшего понятия, что надо сразу. Или тыкните в FAQ"
)


def test_order_advice_question_is_marketplace_commerce():
    assert _topic_is_marketplace_commerce_intent(_ORDER_ADVICE_MSG)
    assert _is_conversational_chatter(_ORDER_ADVICE_MSG)


def test_order_advice_question_no_model_clarify():
    assert not _needs_model_clarification(_ORDER_ADVICE_MSG)


# --- Лог 08:05:55: «Как через экструдер пропустили» ---

_EXTRUDER_THREAD_PAST = "Как через экструдер пропустили"


def test_extruder_thread_past_action_is_observation():
    assert _is_technical_observation_sharing(_EXTRUDER_THREAD_PAST)
    assert _is_conversational_chatter(_EXTRUDER_THREAD_PAST)
    assert not _needs_model_clarification(_EXTRUDER_THREAD_PAST)


def test_extruder_how_to_infinitive_not_caught():
    # Инфинитив — легитимный вики-запрос, не отсекаем
    assert not _is_technical_observation_sharing("Как через экструдер пропустить нить?")


# --- Лог 08:07:51: «не факт что» + «я думал … а сейчас вижу» ---

_EXTRUDER_SPECULATION = (
    "наверное , прикольно. Я думал там кусок такой, тип из экструдера доставали, "
    "а сейчас вижу что вся катушка такая "
    "Только не факт что в экструдере не схватится шестернями за гладкий участок 😂"
)


def test_ne_fakt_chto_is_skepticism():
    assert _is_conversational_skepticism(_EXTRUDER_SPECULATION)


def test_ya_dumal_a_seychas_vizhu_is_opinion():
    assert _is_technical_opinion_sharing(_EXTRUDER_SPECULATION)


def test_extruder_speculation_from_log_is_chatter():
    assert _is_conversational_chatter(_EXTRUDER_SPECULATION)
    assert not _needs_model_clarification(_EXTRUDER_SPECULATION)


# --- Лог 05:01:29: «С партийными печать не интересно как-то становится 😂. Скучно как-то 😁» ---

_PRINT_BOREDOM_MSG = "С партийными печать не интересно как-то становится 😂. Скучно как-то 😁"


def test_print_boredom_opinion_from_log_is_chatter():
    assert _is_technical_opinion_sharing(_PRINT_BOREDOM_MSG)
    assert _is_conversational_chatter(_PRINT_BOREDOM_MSG)
    assert not _needs_model_clarification(_PRINT_BOREDOM_MSG)


# --- Лог 09:01:16: мнение о CAD-софте (AutoCAD/Компас) для 3D-моделирования ---

_CAD_SOFTWARE_OPINION_MSG = (
    "но для 3д моделирования под 3д печать автокад это треш😂"
    "рисую просто потому что знаю все инструменты, но иногда есть куча "
    "лишних движений для чего то простого... поэтому вот всё хочу компас "
    "скачать, но всё времени нет"
)


def test_cad_software_opinion_from_log_is_chatter():
    assert _is_technical_opinion_sharing(_CAD_SOFTWARE_OPINION_MSG)
    assert _is_conversational_chatter(_CAD_SOFTWARE_OPINION_MSG)
    assert not _needs_model_clarification(_CAD_SOFTWARE_OPINION_MSG)


# «Можешь показать качество печать креалти?» — просьба показать конкурента (лог 12:14).
_CREALITY_SHOWCASE = "Можешь показать качество печать креалти?"


def test_creality_spelling_detected():
    # «креалти» — неточное написание Creality, должно распознаваться.
    assert _mentions_competitor_printer("креалти")
    assert _mentions_competitor_printer("криалити")
    assert _mentions_competitor_printer("креалити")


def test_competitor_showcase_request_is_chatter():
    assert _is_competitor_showcase_request(_CREALITY_SHOWCASE)
    assert _is_conversational_chatter(_CREALITY_SHOWCASE)
    assert not _needs_model_clarification(_CREALITY_SHOWCASE)


def test_competitor_showcase_variants():
    assert _is_competitor_showcase_request("покажи качество печати creality")
    assert _is_competitor_showcase_request("что скажешь о bambu lab?")


def test_competitor_migration_to_kobra_not_filtered():
    # Упомянут наш принтер — это реальный запрос о переходе/настройке.
    migrate = "у меня была creality, как настроить такое же качество на kobra s1?"
    assert not _is_competitor_showcase_request(migrate)
    assert not _is_conversational_chatter(migrate)


# Новостной пресс-релиз об анонсе сушилки Creality (лог 19:34).
_CREALITY_NEWS = (
    "Creality представила новую сушилку SpacePi X4S 🔥 · Creality продолжает "
    "расширять линейку решений для 3D-печати и анонсировала новый филаментный "
    "сушильный модуль — SpacePi X4S. Новинка рассчитана на стабильную работу "
    "с современными материалами. Ключевые особенности: двухкамерная система "
    "сушки с нагревом до 110°C, поддержка RFID-синхронизации. По заявлению "
    "компании, устройство снижает риск дефектов во время печати. Creality "
    "также намекнула, что ожидаются и другие новинки."
)


def test_product_news_announcement_is_chatter():
    assert _is_product_news_announcement(_CREALITY_NEWS)
    assert _is_non_wiki_chatter_message(_CREALITY_NEWS)


def test_product_news_short_anonce_detected():
    assert _is_product_news_announcement(
        "Anycubic анонсировала новую сушилку для филамента"
    )


def test_filament_drying_question_not_news():
    # Реальный вопрос про сушку — не отсекаем как новость.
    assert not _is_product_news_announcement("как правильно сушить petg на kobra s1?")


def test_new_firmware_howto_not_news():
    # «вышла новая прошивка, как обновить» — есть help-intent, не новость.
    assert not _is_product_news_announcement(
        "вышла новая прошивка для kobra s1, как обновить?"
    )


# Риторическая претензия к производителю про совместимость ACE (лог 19:43).
_ACE_VENDOR_RHETORIC = (
    "Иначе нахрена они кастрировали новые модели на поддержку первой аськи? "
    "Ведь технически это одинаковые устройства"
)


def test_ace_vendor_rhetoric_is_chatter():
    assert _is_non_wiki_chatter_message(_ACE_VENDOR_RHETORIC)
    assert _is_conversational_chatter(_ACE_VENDOR_RHETORIC)
    assert not _needs_model_clarification(_ACE_VENDOR_RHETORIC)


def test_ace_compat_real_question_not_filtered():
    # Реальный вопрос про совместимость — отвечаем.
    q = "первая аська подходит к kobra s1? как подключить?"
    assert not _is_non_wiki_chatter_message(q)
