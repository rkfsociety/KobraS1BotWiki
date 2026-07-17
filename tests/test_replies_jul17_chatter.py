"""Регрессии по разбору recent_replies 2026-07-17."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_filament_shopping_poll,
    _is_non_wiki_chatter_message,
    _is_parcel_arrival_banter,
    _is_peer_bed_mesh_lecture,
    _is_purchase_deliberation_banter,
    _is_sensor_thread_banter,
    _is_thread_continuation_filler,
    _is_thread_printing_tip,
    _is_warranty_service_sidebar,
)


def test_magnets_cutout_manual_qa():
    msg = (
        "всем привет, кто знает как сделать вырез на модели под магниты? "
        "какой инструмент в слайсере и как"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_petg_stringing_manual_qa():
    msg = (
        "Очень много нитей при печати petg на стандартном профиле kobra X , "
        "уже увеличивал и скорость отката и сам откат , помогает лишь установка температуры в 210°С"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_slicer_not_seeing_printer_manual_qa():
    msg = (
        "Приветствую всех. Чет принтер подключается к сети, а слайсер не видит его . "
        "Поможете разобраться , что случилось?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_static_ip_manual_qa():
    msg = (
        "всем привет, подскажите пожалуйста "
        "есть ли возможность  для kobra s1 зарезервировать ip что бы он всегда получал один и тот же"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_sla_speed_manual_qa():
    msg = "Приветствую. Недавно начал осваивать так печать. Не подскажите максимальную скорость так?"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace_temp_sensor_manual_qa():
    msg = (
        "температуру внутри аськи выставил 45, аська показывает что держит 47. "
        "китайский датчик показывает 42.5"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_parcel_arrival_is_chatter():
    msg = "Вот оно как раз и пришло"
    assert _is_parcel_arrival_banter(msg)
    assert _is_conversational_chatter(msg)


def test_angle_print_tip_is_chatter():
    msg = "Под 45 градусов поставить печать, меньше шансов что сломается"
    assert _is_thread_printing_tip(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_fluorescent_shopping_is_chatter():
    msg = "Всем привет. Посоветуйте пластик флуоресцентный проверенный и где брали."
    assert _is_filament_shopping_poll(msg)
    assert _is_conversational_chatter(msg)


def test_buy_s1_deliberation_is_chatter():
    msg = (
        "Добрый вечер дамы и господа :) "
        "Я тут давненько думаю о смене принтера. "
        "У меня сейчас кубик кобра 2 про. Но долго думаю брать ли S1 "
        "Ведь кроме Petg и PLA врятли буду ещё чем-то печатать. Стоит ли?)"
    )
    assert _is_purchase_deliberation_banter(msg)
    assert _is_conversational_chatter(msg)


def test_warranty_sidebar_is_chatter():
    msg = (
        "Три недели назад ДНС проиграл слушание по гарантии принтера Креалити, "
        "не хотели кривой стол ремонтировать."
    )
    assert _is_warranty_service_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_crooked_bed_service_is_chatter():
    msg = "Та нафиг? На скорость не влияет. И вообще они мне кривой стол выслали. В замен родного кривого"
    assert _is_warranty_service_sidebar(msg)
    assert _is_conversational_chatter(msg)


def test_bed_mesh_lecture_is_chatter():
    msg = (
        "Когда снимите карту стола в программе - закреп технички. "
        "Поймете насколько у вас кривой стол. Для печати больших деталей - это важно"
    )
    assert _is_peer_bed_mesh_lecture(msg)
    assert _is_conversational_chatter(msg)


def test_sensor_banter_is_chatter():
    msg = "Ну да)) датчик филамента.. Странно что он у вас голову и без асе не еп))"
    assert _is_sensor_thread_banter(msg)
    assert _is_conversational_chatter(msg)


def test_monolayer_fragment_is_chatter():
    msg = "Разве что монослой"
    assert _is_thread_continuation_filler(msg)
    assert _is_conversational_chatter(msg)


def test_real_network_question_not_shopping():
    assert not _is_filament_shopping_poll(
        "Подскажите температуру для флуоресцентного PLA на kobra s1"
    )


def test_real_bed_calibration_not_warranty():
    assert not _is_warranty_service_sidebar(
        "Подскажите как откалибровать стол на kobra s1, первый слой не липнет"
    )


def test_error_10409_not_chatter():
    assert not _is_conversational_chatter("Ошибка 10409")
