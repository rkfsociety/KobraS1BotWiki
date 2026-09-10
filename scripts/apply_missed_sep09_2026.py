"""Разбор свежей аналитики missed/recent за 2026-09-02…09.

Добавляет безопасные варианты формулировок к уже проверенным manual-QA,
создаёт два узких FAQ для повторяющихся новых тем и очищает локальные
аналитические очереди после проверки матчей.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bot.manual_qa import (  # noqa: E402
    find_manual_qa_answer,
    load_manual_qa_store,
    save_manual_qa_store,
)


MISSED_PATH = ROOT / "data" / "missed_questions.json"
RECENT_PATH = ROOT / ".cache" / "recent_replies.json"


KEY_UPDATES: dict[str, tuple[str, ...]] = {
    "Скорости печати на Kobra S1": (
        "режиме спорт",
        "режим спорт качество",
        "спорт качество хуже",
        "скорости для качества",
    ),
    "Периодическое обслуживание принтера": (
        "как часто нужно принтер смазывать",
        "как часто смазывать принтер",
        "на каком пробеге сопло",
    ),
    "Калибровка стола и первый слой (Kobra S1)": (
        "автоуровень в меню",
        "полный уровень всей пластины",
        "первый слой с волнами",
        "первый слой с тычками",
        "пластина подымается на углах",
    ),
    "Z-offset (зазор сопла над столом)": (
        "z offset можно регулировать",
        "z offset на самом принтере",
        "сопло высоковато стало",
    ),
    "Сопло царапает печатную платформу": (
        "перед стартом печати цепляет пластину",
        "перед стартом цепляет пластину",
        "пытается поцарапать пластину",
        "принтер царапает пластину",
    ),
    "Когда и какие нужны поддержки": (
        "поддержки отвратительные",
        "поддержки плохо печатаются",
        "сопля ползет на поддержках",
    ),
    "Много нитей (стринги) на PETG": (
        "сопли и нити",
        "много соплей",
        "волосы при печати",
    ),
    "Подтянул ремни XY — качество не изменилось": (
        "сильные полосы по одной стороне",
        "как натянуть ремни",
        "ремни ослаблены",
    ),
    "Подача при Load есть, при печати нет": (
        "перестает давить пластик",
        "печатает без пластика",
        "подача пропадает при печати",
        "после load пластик не выходит",
    ),
    "Ошибка подачи после чистки и замены сопла": (
        "аномальная ошибка засор",
        "ложное засорение",
        "пишет засор хотя чисто",
    ),
    "PETG: какую температуру установить": (
        "максимальная температура стола petg",
        "температура стола для petg",
    ),
    "Нейлон PA6 vs PA12": (
        "печатал нейлоном па6",
        "нейлон на кобре",
        "па6 на кобре",
    ),
    "Сушка филамента": (
        "пластик не сушил",
        "почему пластик влажный",
    ),
    "Обновление прошивки (Kobra S1)": (
        "можно ли откатить прошивку",
        "откатить прошивку",
    ),
    "Фильтр (угольный) для Kobra S1": (
        "запах абс в коридоре",
        "токсичные пары абс",
        "накрыть принтер тканью",
    ),
}


NEW_ENTRIES = (
    {
        "keys": ["расходка kobra x", "какие сопла kobra x", "какие сопла взять", "сопло kobra x", "запасное сопло kobra x"],
        "title": "Расходники и сопло Kobra X",
        "answer": (
            "Для старта достаточно штатного сопла; в запас берите совместимое с Kobra X сопло "
            "того же диаметра и типа. Перед покупкой сверяйте точную версию принтера и хотэнда "
            "по маркировке: у разных комплектов совместимость может отличаться."
        ),
    },
    {
        "keys": ["lw филамент", "lw pla", "lw tpu", "настройки lw", "гайд lw филамент", "гайд по lw"],
        "title": "Настройка LW-филамента",
        "answer": (
            "LW-PLA и LW-TPU настраиваются не как обычный материал: ориентируйтесь на паспорт "
            "конкретной катушки, отдельно подберите температуру, скорость и подачу/flow. Начните "
            "с небольшого теста и проверяйте расширение материала; готового универсального профиля "
            "для всех LW-филаментов нет."
        ),
    },
)


def _upsert_entries(entries: list[dict]) -> int:
    by_title = {e.get("title"): e for e in entries if isinstance(e, dict) and isinstance(e.get("title"), str)}
    changed = 0
    for title, keys in KEY_UPDATES.items():
        entry = by_title.get(title)
        if entry is None:
            continue
        old = list(entry.get("keys") or [])
        merged = old + [key for key in keys if key not in old]
        if merged != old:
            entry["keys"] = merged
            changed += 1

    for raw in NEW_ENTRIES:
        entry = by_title.get(raw["title"])
        if entry is None:
            entry = {**raw, "ts": time.time()}
            entries.insert(0, entry)
            by_title[raw["title"]] = entry
            changed += 1
            continue
        old = list(entry.get("keys") or [])
        merged = old + [key for key in raw["keys"] if key not in old]
        if merged != old or entry.get("answer") != raw["answer"]:
            entry["keys"] = merged
            entry["answer"] = raw["answer"]
            changed += 1
    return changed


def _clear_json_list(path: Path) -> int:
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    count = len(old) if isinstance(old, list) else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]\n", encoding="utf-8")
    return count


def main() -> None:
    entries = load_manual_qa_store()
    changed = _upsert_entries(entries)
    save_manual_qa_store(entries)

    checks = (
        ("режим спорт качество хуже", "Скорости печати на Kobra S1"),
        ("как часто нужно принтер смазывать", "Периодическое обслуживание принтера"),
        ("принтер царапает пластину", "Сопло царапает печатную платформу"),
        ("максимальная температура стола petg", "PETG: какую температуру установить"),
        ("можно ли откатить прошивку", "Обновление прошивки (Kobra S1)"),
        ("какие сопла Kobra X взять", "Расходники и сопло Kobra X"),
        ("есть ли гайд по LW филаментам", "Настройка LW-филамента"),
    )
    for question, expected_title in checks:
        match = find_manual_qa_answer(entries, question)
        assert match is not None, question
        assert match[1] == expected_title, (question, match[1], expected_title)

    missed = _clear_json_list(MISSED_PATH)
    recent = _clear_json_list(RECENT_PATH)
    print(f"manual_qa changed_titles={changed}; cleared missed={missed}; recent={recent}")


if __name__ == "__main__":
    main()
