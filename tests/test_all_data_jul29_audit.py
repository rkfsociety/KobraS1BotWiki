"""Регрессии полного разбора данных и аудита manual_qa 2026-07-29."""

from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import _is_non_wiki_chatter_message
from app.bot.wiki_ranking import _response_wiki_url_acceptable


RECENT_THREAD_NOISE = (
    (
        "я потыкал сопоставление цветов, материалы выбираются, есть защита от выбора "
        "не того материала(ABS в боксе вместо PLA в орке), калибровки перед стартом "
        "печати выключаются, сушка работает по тому-же алгоритму как anycubic slicer."
    ),
    (
        "Не липнет - потому что либо пластина жирная, либо пластик говно, либо "
        "температура не та, либо карту снял с говном на сопле"
    ),
    (
        "из-за того что надо было вынимать низ - поломались втулки, с горе-пополам "
        "надел родной низ и все пошло опять по.... Печать перестала липнуть"
    ),
    "Как будто этот тест хрень какая-то",
    "Почему?",
    "Я тебе с1 с двумя аськами, а ты мне п2с?)",
    "Продолжить и после этого на отмену ?",
    (
        "Друг за другом стоять будут, этот допечатается и когда начнет следующий "
        "печатать, то на паузу поставлю"
    ),
    "То есть это не коректный тест пластика?",
)


def test_recent_thread_noise_is_filtered():
    for message in RECENT_THREAD_NOISE:
        assert _is_non_wiki_chatter_message(message), message


def test_real_fdm_questions_are_not_filtered_by_jul29_rule():
    messages = (
        "Kobra S1 выдаёт ошибку 11511 при загрузке из каждого слота ACE",
        "Как заменить модуль очистки сопла на Kobra S1?",
        "Можно ли печатать TPU через ACE 2 Pro на Kobra X?",
        "После Load пластик не выходит из сопла, что проверить?",
    )
    for message in messages:
        assert not _is_non_wiki_chatter_message(message), message


def test_fdm_group_never_accepts_resin_printer_pages():
    assert not _response_wiki_url_acceptable(
        "печать перестала липнуть",
        "https://wiki.anycubic.com/en/resin-3d-printer/Common/"
        "the-print-platform-is-empty-after-printing",
    )


def test_resin_printer_questions_are_out_of_scope_for_fdm_group():
    messages = (
        "Какая максимальная скорость SLA-печати?",
        "Как настроить экспозицию фотополимерной смолы на Photon Mono?",
        "Недавно начал осваивать так печать. Какая максимальная скорость так?",
    )
    entries = load_manual_qa_store()
    for message in messages:
        assert find_manual_qa_answer(entries, message) is None
        assert _is_non_wiki_chatter_message(message), message


def test_manual_qa_has_only_fdm_scope_and_live_audited_urls():
    invalid_urls = (
        "/resin-3d-printer/",
        "/kobra-s1-combo/nozzle-replacement-guide",
        "/kobra-s1-combo/basic-maintenance-guide",
        "/kobra-s1-combo/replace-build-plate",
        "/kobra-s1-combo/routine-maintenance",
        "/kobra-s1-combo/troubleshooting-abnormal-discharge-of-purge-wiper-material",
        "/kobra-3-combo/nozzle-replacement-guide",
        "/filament-and-resin/ace-pro-2",
        "/fdm-3d-printer/kobra-x/quick-start-guide",
    )
    for entry in load_manual_qa_store():
        answer = entry["answer"].lower()
        assert not any(url in answer for url in invalid_urls), entry["title"]


def test_manual_qa_model_specific_corrections():
    entries = load_manual_qa_store()

    kobra_x = find_manual_qa_answer(entries, "Кобра Хэ, куплено. Что дальше?")
    assert kobra_x
    assert "kobra-x" in kobra_x[0].lower()
    assert "kobra-2" not in kobra_x[0].lower()
    assert find_manual_qa_answer(entries, "Кобра Хэ , куплено. Что дальше ?)))")

    ace_2 = find_manual_qa_answer(
        entries,
        "После окончания катушки в первом слоте ACE 2 Pro автоматически подхватит вторую?",
    )
    assert ace_2
    assert "автоподхват" in ace_2[0].lower()
    assert "одинаков" in ace_2[0].lower()

    s1_tpu = find_manual_qa_answer(entries, "Можно ли TPU через ACE Pro на Kobra S1?")
    assert s1_tpu
    assert "внешн" in s1_tpu[0].lower()
    assert "ace gen 2" in s1_tpu[0].lower()


def test_new_real_questions_get_manual_answers():
    entries = load_manual_qa_store()
    assert find_manual_qa_answer(
        entries,
        "В Али писать через поддержку или напрямую на почту кубику?",
    )
    assert find_manual_qa_answer(
        entries,
        "На Kobra X после разборки ошибка при заправке на все 4 канала",
    )
    assert find_manual_qa_answer(
        entries,
        "В Kobra X разобрал голову, собрал, теперь пишет ошибку при заправке на все 4 канала",
    )


def test_new_status_fragments_are_filtered():
    messages = (
        "Первый засор на 201 часе) кандидат на колдпул, другие методы не помогли",
        "Первый засор на 201 часе) кандидат на кодпул, другие методы не помогли",
        "оно 3 дня карту снимало ?",
    )
    for message in messages:
        assert _is_non_wiki_chatter_message(message), message
