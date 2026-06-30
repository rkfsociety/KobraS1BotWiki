"""Разбор recent_replies (2026-06-30): manual_qa + эвристики."""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA_PATH = ROOT / "data" / "manual_qa.json"
BANTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_banter.py"
FILTER_PATH = ROOT / "app" / "bot" / "heuristics" / "_filter.py"
INIT_PATH = ROOT / "app" / "bot" / "heuristics" / "__init__.py"
TEST_PATH = ROOT / "tests" / "test_replies_jun30_chatter.py"

NEW_QA = [
    {
        "keys": [
            "ace с kobra s1",
            "ace pro s1 совместим",
            "амс с s1",
            "аська с s1",
            "kobra 3 v2 combo ради бокса",
            "одной катушкой kobra 3",
            "бабино держатель",
            "держатель катушки kobra 3",
            "печать одной катушкой kobra 3",
        ],
        "title": "ACE Pro с Kobra 3 — поставить на S1? Одна катушка",
        "answer": (
            "Речь про ACE Pro (мультибокс Anycubic), не Bambu AMS — это разные системы.\n\n"
            "ACE Pro совместим и с Kobra S1, и с Kobra 3: до двух ACE на принтер, до 8 цветов "
            "(нужен ещё Filament Hub / 8-in-1 модуль для полного мультицвета). Бокс от Kobra 3 V2 Combo "
            "обычно заводится на S1 после привязки, актуальной прошивки S1 и правильной коммутации.\n\n"
            "Печать одной катушкой на Kobra 3: в слайсере один материал/цвет, без многоцветного режима; "
            "подача с бокового держателя или через один слот ACE. Переделывать принтер не нужно — "
            "достаточно настроек в слайсере.\n\n"
            "Боковой держатель катушки: у версии Combo комплект ориентирован на ACE; для чисто одноцветной "
            "печати без ACE смотрите, что в коробке вашей ревизии (часто держатель есть или докупается/печатается). "
            "У non-combo Kobra 3 штатный держатель обычно в комплекте.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/fdm-3d-printer/ace-pro/multi-device"
        ),
    },
    {
        "keys": [
            "силк пластик",
            "silk pla",
            "silk пластик",
            "впервые силк",
            "советы к печати силк",
            "температуры силк pla",
            "шелковый pla",
        ],
        "title": "Silk PLA (силк) — первые советы",
        "answer": (
            "Silk PLA печатается почти как обычный PLA, но блеск чувствителен к скорости и потоку:\n\n"
            "• Температура: начните с 200–215°C сопло, стол 50–60°C — смотрите таблицу на катушке "
            "(часто как у PLA или на 5°C выше).\n"
            "• Внешние стенки печатайте медленнее (30–50 мм/с) — так блеск ровнее.\n"
            "• Обдув умеренный; слишком сильный «матовит» поверхность.\n"
            "• Храните сухо; влажный silk даёт пузыри и тусклость.\n"
            "• Через ACE Pro неофициальный/жёсткий silk может капризничать — для первых тестов лучше "
            "прямая подача с держателя.\n\n"
            "Офиц. источник: https://wiki.anycubic.com/en/filament-and-resin/filament-guide"
        ),
    },
]

NEW_BANTER_FN = '''

def _is_figurative_mood_remark(text: str) -> bool:
    """«Такое чувство что перед граблями…», «3д печать — дешёвое хобби» — настроение треда, не вопрос."""
    if not text or not text.strip():
        return False
    t = re.sub(r"\\s+", " ", text.lower()).strip()
    if _HELP_GUARD_RE.search(t):
        return False
    if re.search(r"\\b(?:помогите|подскаж|как\\s+(?:настро|почин|сделать)|что\\s+делать|не\\s+работает)\\b", t):
        return False
    if re.search(r"\\bперед\\s+граблями\\b", t):
        return True
    if re.search(r"\\bтакое\\s+(?:чувство|ощущение)\\s+что\\b", t):
        return True
    if re.search(r"\\b3[дd]\\s*печат\\w*\\b", t) and re.search(r"\\bдешев\\w*\\s+хобби\\b", t):
        return True
    if re.search(r"\\bкапец\\s+как\\s+дешев\\w*\\b", t) and re.search(r"\\b(?:хобби|печат)\\w*\\b", t):
        return True
    return False
'''

TEST_CONTENT = '''"""Регрессии по разбору recent_replies 2026-06-30."""
from __future__ import annotations

from app.bot.manual_qa import find_manual_qa_answer
from app.bot.text_heuristics import (
    _is_conversational_chatter,
    _is_figurative_mood_remark,
    _is_non_wiki_chatter_message,
)


def test_ace_s1_compatibility_manual_qa():
    msg = (
        "хочу купить Kobra 3 V2 Combo ради бокса амс. "
        "Подскажите амс-ка же без проблем должна завестись с s1?"
    )
    assert find_manual_qa_answer(msg)


def test_silk_pla_manual_qa():
    msg = "Впервые взял силк пластик, какие советы к его печати?"
    assert find_manual_qa_answer(msg)


def test_grabli_mood_is_chatter():
    msg = "Такое чувство что перед граблями очередь стоит…"
    assert _is_figurative_mood_remark(msg)
    assert _is_conversational_chatter(msg)


def test_cheap_hobby_opinion_is_chatter():
    msg = "Такое ощущение что кто то где то сказал что 3д печать это капец как дешевое хобби"
    assert _is_figurative_mood_remark(msg)
    assert _is_non_wiki_chatter_message(msg)


def test_real_silk_question_not_chatter():
    assert not _is_figurative_mood_remark(
        "Впервые взял силк пластик, какие советы к его печати?"
    )


def test_real_ace_question_not_chatter():
    assert not _is_figurative_mood_remark(
        "Подскажите ace pro заведётся на kobra s1?"
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

    # поправить склейку после прошлого патча
    t = t.replace(
        "    return True\ndef _is_vague_fix_without_symptom",
        "    return True\n\n\ndef _is_vague_fix_without_symptom",
    )

    if "_is_figurative_mood_remark" not in t:
        anchor = "def _is_vague_fix_without_symptom(text: str) -> bool:"
        t = t.replace(anchor, NEW_BANTER_FN.lstrip("\n") + anchor)

    BANTER_PATH.write_text(t, encoding="utf-8")


def patch_filter() -> None:
    t = FILTER_PATH.read_text(encoding="utf-8")
    old = "        or _is_offtopic_work_life_sidebar(text)\n    )"
    new = (
        "        or _is_offtopic_work_life_sidebar(text)\n"
        "        or _is_figurative_mood_remark(text)\n"
        "    )"
    )
    if "_is_figurative_mood_remark" not in t and old in t:
        t = t.replace(old, new)
    FILTER_PATH.write_text(t, encoding="utf-8")


def patch_init() -> None:
    t = INIT_PATH.read_text(encoding="utf-8")
    old = "    _is_filament_brand_social_chat,\n"
    new = "    _is_filament_brand_social_chat,\n    _is_figurative_mood_remark,\n"
    if "_is_figurative_mood_remark" not in t and old in t:
        t = t.replace(old, new)
    INIT_PATH.write_text(t, encoding="utf-8")


def write_tests() -> None:
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")


def main() -> None:
    patch_manual_qa()
    patch_banter()
    patch_filter()
    patch_init()
    write_tests()
    print(f"Added {len(NEW_QA)} manual_qa entries + figurative mood filter")


if __name__ == "__main__":
    main()
