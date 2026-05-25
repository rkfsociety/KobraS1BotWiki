"""
Справочник по моделям Anycubic (локально в боте): открытый/закрытый корпус, есть ли камера со дверью.

Приставка Combo у Anycubic — это комплектация: в коробке вместе с принтером идёт ACE Pro
(первая или вторая версия), а не «другой корпус». Корпус и дверь/рама совпадают с версией без Combo.
Пополняйте по мере необходимости — вики не всегда явно говорит про конструкцию.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Frame = Literal["open", "enclosed", "unknown"]


@dataclass(frozen=True)
class PrinterProfile:
    slug: str
    display_ru: str
    frame: Frame
    #: False — точно нет типовой стеклянной двери камеры (открытая рама и т.п.)
    has_chamber_door: bool | None
    size_note_ru: str = ""
    note_ru: str = ""


_PROFILES: tuple[PrinterProfile, ...] = (
    PrinterProfile(
        slug="kobra-3-combo",
        display_ru="Anycubic Kobra 3",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Тот же корпус, что у Kobra 3; Combo — в комплекте ACE Pro (v1 или v2).",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-s1-combo",
        display_ru="Anycubic Kobra S1",
        frame="enclosed",
        has_chamber_door=True,
        size_note_ru="Тот же принтер, что Kobra S1; Combo — в комплекте ACE Pro (v1 или v2).",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-s1",
        display_ru="Anycubic Kobra S1",
        frame="enclosed",
        has_chamber_door=True,
        size_note_ru="Закрытая камера со стеклом/дверью; без ACE Pro в комплекте (в отличие от Combo).",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-3",
        display_ru="Anycubic Kobra 3",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Открытая рама «bedslinger»; без ACE Pro в комплекте (в отличие от Combo).",
        note_ru="У этой модели нет отдельной стеклянной двери камеры как у закрытых станков — корпус открытого типа.",
    ),
    PrinterProfile(
        slug="kobra-2",
        display_ru="Anycubic Kobra 2",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Открытая конструкция линейки Kobra 2.",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-go",
        display_ru="Anycubic Kobra Go",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Компактная открытая рама.",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-neo",
        display_ru="Anycubic Kobra Neo",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Открытая рама.",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-max-combo",
        display_ru="Anycubic Kobra Max",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Тот же принтер, что Kobra Max; Combo — в комплекте ACE Pro (v1 или v2).",
        note_ru="",
    ),
    PrinterProfile(
        slug="kobra-max",
        display_ru="Anycubic Kobra Max",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Крупный формат, открытая рама; в продаже часто «Kobra 3 Max». Без ACE Pro в комплекте (в отличие от Combo).",
        note_ru="Если установлена сторонняя камера — это уже не заводская «дверь».",
    ),
    PrinterProfile(
        slug="vyper",
        display_ru="Anycubic Vyper",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Открытая рама; боковины при необходимости докупаются отдельно.",
        note_ru="",
    ),
    PrinterProfile(
        slug="chiron",
        display_ru="Anycubic Chiron",
        frame="open",
        has_chamber_door=False,
        size_note_ru="Большой открытый корпус.",
        note_ru="",
    ),
)

_BY_SLUG: dict[str, PrinterProfile] = {p.slug: p for p in _PROFILES}


def profile_by_slug(slug: str) -> PrinterProfile | None:
    return _BY_SLUG.get(slug)


def pick_profile_for_hints(hints: frozenset[str]) -> PrinterProfile | None:
    """Берём самый специфичный профиль по slug (вариант Combo — только комплектация ACE Pro)."""
    if not hints:
        return None
    priority = (
        "kobra-3-combo",
        "kobra-s1-combo",
        "kobra-max-combo",
        "kobra-s1",
        "kobra-3",
        "kobra-2",
        "kobra-max",
        "kobra-go",
        "kobra-neo",
        "vyper",
        "chiron",
    )
    for slug in priority:
        if slug in hints:
            return _BY_SLUG.get(slug)
    return None


def explain_resonance_pa_oscillations(question: str) -> str | None:
    """Затухающие колебания: резонанс vs PA — не случайный layer-shift чужой модели."""
    from app.bot.text_heuristics import _topic_is_resonance_pa_tuning_intent

    if not _topic_is_resonance_pa_tuning_intent(question):
        return None
    return (
        "Затухающие «волны»/колебания на отпечатке чаще связаны с **резонансом (ringing)**, а не с PA:\n"
        "• **Input Shaping / виброкомпенсация** — основной инструмент; автокалибровка как раз про это "
        "(по оси X/Y). Если «не влияет» — проверьте, что профиль/shaper сохранён и тест на той же скорости, "
        "что в печати.\n"
        "• Снизите jerk/acceleration на пробном кубе; иногда помогает ужесточение рамы.\n"
        "• **PA (Pressure Advance)** — про поток в углах/поворотах экструдера, обычно не «затухающие волны» "
        "по всей детали; калибруется отдельным тестом.\n"
        "• **Сдвиг слоя** — другое явление (ступеньки), не затухающий паттерн.\n"
        "Напишите модель (Kobra S1 / 3 / …) и слайсер — подскажу, где в вики искать shaper/калибровку именно для неё."
    )


def explain_slicer_mouse_ear_removal(question: str) -> str | None:
    """Убрать «ушко» / mouse ear в слайсере — не quick start вики."""
    from app.bot.text_heuristics import _topic_is_slicer_feature_help_intent

    if not _topic_is_slicer_feature_help_intent(question):
        return None
    return (
        "«Ушко» в слайсере обычно — mouse ear (ушко brim) или добавленный диск поддержки.\n"
        "• Выделите модель → Brim / Поддержки → отключите Mouse ears (или аналог в вашей версии).\n"
        "• Если ушки уже на столе: удалите лишние объекты на платформе или пересоздайте brim без mouse ears.\n"
        "• Если «ушко» в самой STL — правка в CAD; в слайсере иногда помогает обрезка/модификатор (зависит от версии).\n"
        "Общий quick start кнопку не показывает — пришлите скрин панели Brim/Support, если пункт не найдёте."
    )


def explain_slicer_vertical_holes(question: str) -> str | None:
    """Отверстия в вертикальных стенках: капля в CAD или настройки слайсера — не quick start вики."""
    from app.bot.text_heuristics import _topic_is_slicer_vertical_hole_intent

    if not _topic_is_slicer_vertical_hole_intent(question):
        return None
    return (
        "Круглое отверстие в вертикальной стенке FDM часто «сплющивает» сверху: верхняя дуга — нависание, "
        "пластик не держит свод.\n"
        "• В модели: отверстие «каплей» (teardrop) или dogbone — надёжнее всего.\n"
        "• В слайсере: horizontal expansion / расширение отверстий, иногда настройки моста на верхней дуге "
        "(зависит от Orca/Cura/PrusaSlicer).\n"
        "• Альтернатива: вынести отверстие в горизонтальную грань или слегка усилить верх дугой.\n"
        "Общий quick start по слайсеру эту тему не закрывает — подбирайте параметры под материал."
    )


def explain_door_vs_design(question: str, hints: frozenset[str]) -> str | None:
    """
    Если спрашивают про дверь камеры, а по каталогу у модели её нет — возвращаем готовый ответ.
    """
    tl = question.lower()
    door_ask = any(
        k in tl
        for k in (
            "двер",
            "door",
            "петл",
            "hinge",
            "enclosure",
            "glass door",
        )
    ) or ("камер" in tl and "стекл" in tl)
    if not door_ask:
        return None

    prof = pick_profile_for_hints(hints)
    if prof is None or prof.has_chamber_door is not False:
        return None

    if prof.frame == "open":
        return (
            "Возможно, вы имели в виду другую модель: у "
            f"{prof.display_ru} нет заводской двери камеры — это открытая рама, не закрытый корпус со дверью."
        )
    return (
        "Возможно, вы имели в виду другую модель: у "
        f"{prof.display_ru} нет типовой заводской двери камеры — в базовой комплектации такой детали нет."
    )

