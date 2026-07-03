"""Разбор recent_replies (2026-07-03): manual_qa + эвристики."""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "data" / "manual_qa.json"
BANTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_banter.py"
FILTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_filter.py"
INIT_PATH = ROOT / "app" / "bot" / "heuristics" / "__init__.py"
TEST_PATH = ROOT / "tests" / "test_replies_jul03_chatter.py"
RECENT_PATH = ROOT / ".cache" / "recent_replies.json"

NEW_QA = [
    {
        "keys": [
            "более мягкий на s1",
            "95а не мягк",
            "мягкий tpu на s1",
            "танцы должны быть",
            "shore tpu",
            "печатать мягкий tpu",
            "мягче tpu s1",
        ],
        "title": "Мягкий TPU (Shore) на Kobra S1",
        "answer": (
            "Shore 95A — «мягкий» TPU только по сравнению с жёсткими пластиками; "
            "при комнатной температуре он всё равно плотный.\n\n"
            "Для реально мягких деталей (чехлы, накладки):\n"
            "• Берите TPU 85A или ниже (если продавец указывает Shore) — на Kobra S1 печатаются, "
            "но медленно (15–30 мм/с), ретракт минимальный, прямая подача предпочтительнее ACE.\n"
            "• Сушите TPU перед печатью.\n"
            "• Для гибких крупных деталей — тонкие стенки и заполнение 10–20%.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/print-tpu"
        ),
    },
    {
        "keys": [
            "смоделить такую ручку",
            "чехолчик из тпу",
            "чехол из тпу",
            "неровностей и скруглений",
            "скопировать форму ручки",
            "моделировать ручку точно",
        ],
        "title": "Как смоделировать сложную ручку под чехол TPU",
        "answer": (
            "Для точной копии формы с множеством скруглений:\n\n"
            "• Фотограмметрия — сфотографируйте ручку со всех сторон "
            "(телефон + Polycam/Meshroom), получите облако точек и подчистите в Meshmixer/Blender.\n"
            "• Калипер + эскиз — для простых форм замерьте сечения и постройте loft/sweep в Fusion/FreeCAD.\n"
            "• Силиконовая форма + скан — если ручка съёмная, сделайте слепок и отсканируйте.\n"
            "• В модели чехла оставьте зазор 0.3–0.5 мм под усадку TPU; печатайте стенки 2–3 периметра, "
            "заполнение 15–25%.\n\n"
            "Это общие приёмы моделирования — не специфика Anycubic, но для чехла из TPU подходят."
        ),
    },
    {
        "keys": [
            "принудительной подаче подача есть",
            "при печати нет подач",
            "подача есть при подаче",
            "при печати нет",
            "греет при подаче",
            "при принудительной подаче",
        ],
        "title": "Подача при Load есть, при печати нет",
        "answer": (
            "Если при принудительной подаче (Load/Purge) пластик идёт нормально, а при старте печати пропадает:\n\n"
            "• В паузе между подачами сопло остывает — первые секунды печати давление не успевает восстановиться. "
            "Подождите 5–10 с после preheat или включите prime line / башню в слайсере.\n"
            "• Проверьте, что в профиле верный материал и температура (для PLA обычно 200–215°C сопло, 50–60°C стол).\n"
            "• Слабый прижим ролика экструдера или проскальзывание на катушке.\n"
            "• Забитый хотэнд проявляется именно под нагрузкой — cold pull или замена сопла.\n"
            "• В ACE — повторите цикл Unload/Load, убедитесь что нить не перекручена в PTFE.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/troubleshooting-abnormal-print-head-clogging"
        ),
    },
    {
        "keys": [
            "прогонять пластик до печати",
            "забивается в радиаторе",
            "ошибка при подготовки печати",
            "забивается при подготовке",
            "heat creep",
            "идеально идёт до печати",
        ],
        "title": "Прогон OK, при старте печати засор (heat creep)",
        "answer": (
            "Симптом: purge/load идёт ровно, а при подготовке или первых слоях печати забивается хотэнд "
            "(часто ошибка подачи):\n\n"
            "• Heat creep — филамент размягчается высоко в теплоизоляции и клинит. Снизьте температуру сопла "
            "к нижней границе профиля, уменьшите время preheat.\n"
            "• Проверьте прижим ролика, состояние PTFE-трубки и установку сопла (термопаста/зазор).\n"
            "• Новое сопло — убедитесь в правильном моменте затяжки и что хотэнд собран без перекоса.\n"
            "• Печатайте первые слои медленнее; отключите лишние движения в начале (bed mesh, wipe tower) для теста.\n"
            "• Cold pull или замена сопла, если клин остался.\n\n"
            "Офиц. источник: "
            "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/troubleshooting-abnormal-print-head-clogging"
        ),
    },
    {
        "keys": [
            "нож который режет филамент",
            "режет филамент не срабатывает",
            "грешу на нож",
            "резак филамента",
            "не режет филамент",
            "cutter не работает",
        ],
        "title": "Нож/резак филамента не срабатывает",
        "answer": (
            "На Kobra S1 Combo в ACE стоит нож для обрезки нити при смене материала.\n\n"
            "Если не режет / не срабатывает:\n"
            "• Проверьте, что обрезок не застрял в лотке и механизм свободен.\n"
            "• В меню ACE выполните смену филамента — нож должен щёлкнуть в конце выгрузки.\n"
            "• Обновите прошивку ACE и принтера.\n"
            "• При износе или поломке — замена модуля резака по инструкции.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/cutter-replacement"
        ),
    },
]

NEW_BANTER_FN = '''

def _is_ace_meta_banter(text: str) -> bool:
    """«Что вы там на аську жалуетесь» — мета-болтовня про ACE в треде, не вопрос."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    ace = bool(re.search(r"\\b(?:ась\\w*|ace|амс)\\b", t))
    if ace and re.search(r"\\bчто\\s+вы\\s+там\\b", t):
        return True
    if ace and re.search(r"\\bжалует\\w*\\b", t) and not re.search(
        r"\\b(?:не\\s+работает|ошибк|слом|помогите|подскаж)\\b", t
    ):
        return True
    return False


def _is_personal_upholstery_project_sidebar(text: str) -> bool:
    """«Ткань не охота… кресло обновить» — обсуждение своего проекта, не вопрос к боту."""
    if not text or not text.strip() or "?" in text:
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.search(r"\\b(?:подскаж|помогите|как\\s+(?:сделать|настро|печат))\\b", t):
        return False
    material_choice = bool(
        re.search(r"\\bткань\\b", t) and re.search(r"\\b(?:мягк\\w*\\s+пластик|тпу|tpu)\\b", t)
    )
    project = bool(re.search(r"\\b(?:кресл\\w*|обновить|набить|руку)\\b", t))
    return material_choice and project
'''

CONTINUATION_PATCH_OLD = """    if re.search(r"\\bразве\\s+нет\\b", t):
        return True
    return False"""


CONTINUATION_PATCH_NEW = """    if re.search(r"\\bразве\\s+нет\\b", t):
        return True
    if re.match(r"^это\\s+ж\\s+(?:во\\s+)?время", t):
        return True
    if re.search(r"\\bпечатат\\w*\\s+прям\\s+или\\s+как\\b", t):
        return True
    return False"""

TEST_CONTENT = '''"""Регрессии по разбору recent_replies 2026-07-03."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer, load_manual_qa_store
from app.bot.text_heuristics import (
    _is_ace_meta_banter,
    _is_conversational_chatter,
    _is_non_wiki_chatter_message,
    _is_personal_upholstery_project_sidebar,
    _is_thread_continuation_filler,
)


def test_softer_tpu_shore_manual_qa():
    msg = (
        "Тпу, по крайней мере 95а нифига мягкой не будет при комнатной температуре, "
        "а что б более мягкий на с1 печатать еще те танцы должны быть"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_handle_modeling_manual_qa():
    msg = (
        "Пожалуйста подскажите, как можно смоделить такую ручку максимально точно, "
        "неровностей и скруглений куча, хочу ей сделать чехолчик из тпу"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_load_ok_print_fail_manual_qa():
    msg = (
        "На принудительной подаче подача есть, а при печати нет. "
        "Я не печатаю пла и не знаю на скок он греет при подаче, так ж как у всех 250?"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_heat_creep_on_print_start_manual_qa():
    msg = (
        "Если прогонять пластик до печати то он идеально идёт. Новое сопло поставил. "
        "Но как только ставишь на печать деталь происходит какой то баг при подготовки печати "
        "и вылетает ошибка забивается он в радиаторе"
    )
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_filament_cutter_manual_qa():
    msg = "Парни подскажите что делать? Грешу на нож который режет филамент он походу не срабатывает"
    assert find_manual_qa_answer(load_manual_qa_store(), msg)


def test_ace_meta_banter_is_chatter():
    msg = "Что вы там на аську жалуетесь 😂"
    assert _is_ace_meta_banter(msg)
    assert _is_conversational_chatter(msg)


def test_chair_upholstery_sidebar_is_chatter():
    msg = (
        "Ткань как то не охото, учитывая что это мягкий пластик и с ним комфортно, "
        "а тут как раз и кресло обновить и руку набить по возможности"
    )
    assert _is_personal_upholstery_project_sidebar(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_print_timing_continuation_is_chatter():
    msg = "это ж во время печатати прям или как?"
    assert _is_thread_continuation_filler(msg)
    assert _is_conversational_chatter(msg)


def test_real_cutter_question_not_chatter():
    assert not _is_ace_meta_banter(
        "Нож режет филамент не срабатывает, что делать на kobra s1?"
    )


def test_real_tpu_modeling_not_sidebar():
    assert not _is_personal_upholstery_project_sidebar(
        "Подскажите как смоделить ручку под чехол из тпу?"
    )
'''


def patch_manual_qa() -> None:
    entries = json.loads(QA_PATH.read_text(encoding="utf-8"))
    now = time.time()
    for i, e in enumerate(NEW_QA):
        entries.insert(
            0,
            {
                "keys": e["keys"],
                "title": e["title"],
                "answer": e["answer"],
                "ts": now - i * 0.001,
            },
        )
    QA_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def patch_banter() -> None:
    t = BANTER_PATH.read_text(encoding="utf-8")
    if CONTINUATION_PATCH_OLD in t:
        t = t.replace(CONTINUATION_PATCH_OLD, CONTINUATION_PATCH_NEW)
    if "_is_ace_meta_banter" not in t:
        anchor = "def _is_vague_fix_without_symptom(text: str) -> bool:"
        t = t.replace(anchor, NEW_BANTER_FN.lstrip("\n") + anchor)
    BANTER_PATH.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    for name in ("_is_ace_meta_banter", "_is_personal_upholstery_project_sidebar"):
        old_import = "    _is_figurative_mood_remark,\n)"
        new_import = f"    _is_figurative_mood_remark,\n    {name},\n)"
        if name not in t and old_import in t:
            t = t.replace(old_import, new_import, 1)
            old_import = f"    _is_figurative_mood_remark,\n    {name},\n)"
    old_chain = "        or _is_figurative_mood_remark(text)\n    )"
    new_chain = (
        "        or _is_figurative_mood_remark(text)\n"
        "        or _is_ace_meta_banter(text)\n"
        "        or _is_personal_upholstery_project_sidebar(text)\n"
        "    )"
    )
    if "_is_ace_meta_banter(text)" not in t and old_chain in t:
        t = t.replace(old_chain, new_chain)
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    t = INIT_PATH.read_text(encoding="utf-8")
    additions = (
        "    _is_ace_meta_banter,\n"
        "    _is_personal_upholstery_project_sidebar,\n"
    )
    old = "    _is_figurative_mood_remark,\n    _is_general_thread_sidebar,\n"
    new = "    _is_figurative_mood_remark,\n" + additions + "    _is_general_thread_sidebar,\n"
    if "_is_ace_meta_banter" not in t and old in t:
        t = t.replace(old, new)
    INIT_PATH.write_text(t, encoding="utf-8")


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def clear_recent_replies() -> None:
    RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECENT_PATH.write_text("[]\n", encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    write_tests()
    clear_recent_replies()
    print(f"Added {len(NEW_QA)} manual_qa + 2 banter filters + continuation filler")


if __name__ == "__main__":
    main()
