"""Регрессии по разбору missed_questions 2026-07-04."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_non_wiki_chatter_message,
    _is_offtopic_auto_sidebar,
)


def test_resonance_manual_qa():
    entries = load_manual_qa_store()
    msg = (
        "Люди, у меня странный вопрос. Есть на s1 какой-то секретный секрет борьбы с резонансом? "
        "Я уже ремни перетянул, и калибровку калибровал, и смазал всё, а всё равно на скоростях "
        "60-100 гудит и волны пускает"
    )
    assert find_manual_qa_answer(entries, msg)


def test_nozzle_wrench_manual_qa():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "Какой ключ нужен для сопла s1?")


def test_cooling_slowdown_manual_qa():
    entries = load_manual_qa_store()
    msg = "В охлаждении прутка - замедления отключены ? ( галочка стоит?)"
    assert find_manual_qa_answer(entries, msg)


def test_firmware_download_manual_qa():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "есть где скачать 2.6.0.0?")


def test_petg_50c_manual_qa():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(entries, "Всм 50 градусов на петг?")


def test_tpu_shore_manual_qa():
    entries = load_manual_qa_store()
    msg = "При +20 95а эластичный но нифига не мягкий. Мягкий он после +60"
    assert find_manual_qa_answer(entries, msg)


def test_logan_car_chat_is_chatter():
    assert _is_offtopic_auto_sidebar("Логан и Сандero плохие машины?)")


def test_vw_engine_chat_is_chatter():
    assert _is_offtopic_auto_sidebar("Восьмиклоп это как 1.6 атмо у вага. Никуда не разгоняется")


def test_benzin_nostalgia_is_chatter():
    assert _is_offtopic_auto_sidebar("Я еще помню времена до короны когда бензин стоил 53 рубля")


def test_speed_poll_is_chatter():
    assert _is_non_wiki_chatter_message("всем привет А кто на каких скоростях печатает на кубике?")


def test_klipper_update_nag_is_chatter():
    msg = (
        "Клиппер обновил наверное? Теперь обновляй мцу, плату головы и картографер. "
        "Там же написано, что клиппер новее прошивок мцу твоих, собирай и обновляй"
    )
    assert _is_non_wiki_chatter_message(msg)


def test_real_nozzle_help_not_chatter():
    assert not _is_non_wiki_chatter_message("Какой ключ нужен для сопла s1?")
