"""Регрессии по ошибочным ответам из data/bad_answers.json.

Все эти реплики бот раньше принимал за вопросы и отвечал ссылкой из вики.
Теперь они должны распознаваться как болтовня и не получать ответа.
"""
from __future__ import annotations

from app.bot.text_heuristics import (
    _is_bare_combo_variant_fragment,
    _is_bare_fragment_question,
    _is_community_experience_poll,
    _is_competitor_model_disambiguation,
    _is_content_post_request,
    _is_conversational_chatter,
    _is_firmware_slicer_version_gossip,
    _is_marketplace_search_chatter,
    _is_multicolor_tower_rhetoric,
    _is_non_wiki_chatter_message,
    _is_peer_diagnostic_checklist,
    _is_private_money_contact_spam,
    _is_profanity_outburst_chatter,
    _is_social_location_question,
    _is_thread_continuation_filler,
    _is_thread_bed_surface_opinion,
    _is_thread_humor_meme,
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


# --- разбор «последних ответов»: бот отвечал на болтовню/фрагменты ---

def test_slicer_preview_chatter_is_chatter():
    assert _is_conversational_chatter("Как слайсер нарезал")
    assert _is_conversational_chatter("Как нарезает слайсер")
    assert _is_conversational_chatter("Сделайте видео как Слайсер нарезал деталь")


def test_profile_tweak_account_is_chatter():
    assert _is_conversational_chatter(
        "Ну, а профиль Андрея . Максимум что я там сделал, так это снизил скорость внешке с 180 до 150"
    )


def test_solo_recollection_is_chatter():
    assert _is_conversational_chatter(
        "Помню кто-то писал что 600+ надо. Думаю если печать объёмная - лучше поэкспериментировать"
    )


def test_personal_opinion_remark_is_chatter():
    assert _is_conversational_chatter("Поддержками с ветками тебе там все портит как мне кажется")


def test_filler_what_to_do_is_chatter():
    assert _is_conversational_chatter("Но что поделать")


# --- реальные слайсер/профиль вопросы не блокируются ---

def test_real_slicer_questions_not_chatter():
    assert not _is_conversational_chatter("почему слайсер не нарезает модель?")
    assert not _is_conversational_chatter("как сделать поддержки в слайсере?")
    assert not _is_conversational_chatter("как настроить скорость внешнего периметра на kobra s1?")


# --- ещё партия «последних ответов»: фрагменты, догадки, размышления ---

def test_bare_fragment_questions_are_chatter():
    assert _is_conversational_chatter("Булочка же?")
    assert _is_conversational_chatter("Как и многоцветом")


def test_planning_musing_is_chatter():
    assert _is_conversational_chatter("Вот думал попробовать что то с кольцевым нагревателем")


def test_photo_observation_musing_is_chatter():
    assert _is_conversational_chatter(
        "Кстати, на последнем фото видны изъяны на поверхности, думаю, что диаметр прутка гулял"
    )


def test_peer_past_action_question_is_chatter():
    assert _is_conversational_chatter("Или ты уже разложил в слайсере?")


def test_diagnostic_bin_question_is_chatter():
    assert _is_conversational_chatter("Мусорку не цепляет?")


def test_infinitive_howto_not_chatter():
    # «как разложить детали» — это how-to, не вопрос соседу о прошлом действии.
    assert not _is_conversational_chatter("как разложить детали в слайсере?")
    assert not _is_conversational_chatter("на фото видно дефект, как исправить?")


# --- разбор missed_questions 2026-06 ---

def test_community_experience_poll_is_chatter():
    assert _is_community_experience_poll(
        "У кого сколько наработки печати по часам? Что из серьёзного уже меняли на принтере?"
    )
    assert _is_community_experience_poll(
        "Всем привет! Хочу взять первый 3д принтер, смотрю на Anycubic Kobra X. "
        "Можете сказать что плохое о нём, что хорошее?"
    )
    assert _is_conversational_chatter(
        "ребят вопрос не по тебе кто то может помочь с эндером 3 про ?"
    )


def test_private_money_spam_is_chatter():
    assert _is_private_money_contact_spam("Не хватает бабла? Черкани мне в приватные выручу)")


def test_firmware_gossip_fragment_is_chatter():
    assert _is_firmware_slicer_version_gossip("ещё как вариант 2.7.0.9")
    assert _is_bare_fragment_question("Не такой ?")


def test_thread_humor_is_chatter():
    assert _is_thread_humor_meme("Он просто не может выехать из-за того , что сопля петга затвердела")


def test_real_help_not_missed_chatter_filters():
    assert not _is_community_experience_poll(
        "Всем привет! Подскажите, печатаю кашпо, на одном месте залом. Корба s1, petg"
    )
    assert not _is_firmware_slicer_version_gossip("как обновить прошивку до 2.7.2.7 на kobra s1?")
    assert not _is_thread_humor_meme("почему petg не липнет к столу на kobra s1?")


# --- разбор recent_replies / bad_answers 2026-06 (отвеченные) ---

def test_ace_price_shopping_chatter():
    assert _is_conversational_chatter("Где аськи по 5 тыщ")
    assert _is_conversational_chatter("Тысячи 2-3?)")


def test_fitting_fragment_is_chatter():
    assert _is_bare_fragment_question("Фитинг?")
    assert _is_conversational_chatter("Фитинг?")


def test_resume_print_continuation_is_chatter():
    msg = "А почему?\nПросто раньше ещё не приходилось возобновлять печать"
    assert _is_thread_continuation_filler(msg)
    assert _is_conversational_chatter(msg)


def test_peer_flow_reply_is_chatter():
    msg = "А как поток? \nОбъемый расход? \nТы в тот раз сказал что тест хрегь ставь 22"
    assert _is_conversational_chatter(msg)


def test_kapton_opinion_is_chatter():
    msg = "На кой там каптон? Там и обычного хватит, температура головы никакая."
    assert _is_conversational_chatter(msg)


def test_bot_appreciation_meta_is_chatter():
    assert _is_conversational_chatter(
        "Он очень часто помогает всем. Когда админов нет в свободном доступе"
    )


def test_peer_past_action_relay_is_chatter():
    assert _is_thread_continuation_filler("Тот кто писал - не стачивал")
    assert _is_conversational_chatter("Тот кто писал - не стачивал")


def test_vague_fix_without_symptom_is_chatter():
    msg = (
        "Добрый день, опыт в печати и пользовании к сожалению скудный, "
        "подскажите пожалуйста как такое чинится? Anycubic Kobra s1"
    )
    assert _is_conversational_chatter(msg)


def test_real_asa_outdoor_not_chatter():
    assert not _is_conversational_chatter("ASA филамент для улицы какая температура?")
    assert not _is_thread_bed_surface_opinion("как наклеить каптон на стол kobra s1?")
