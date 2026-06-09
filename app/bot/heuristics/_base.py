"""Примитивы: regex-константы и базовые функции без внешних зависимостей."""
from __future__ import annotations

import re


_PRINTER_MENTION_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"kobra|photon|vyper|chiron|predator|anycubic|megax|mega[\s-]?x|mega[\s-]?pro|mega[\s-]?s|"
    r"wash[\s-]?(and|&)?[\s-]?cure|mono[\s-]?m|m5s|"
    r"кобра|фотон|вайпер|аникубик"
    r")(?![a-z0-9])"
)


def _printer_mentioned(text: str) -> bool:
    """В тексте явно названа линейка/семейство принтера (латиница или кириллица)."""
    if _PRINTER_MENTION_RE.search(text):
        return True
    tl = text.lower()
    # номера серий часто пишут отдельно: "s1", "k2", "m5" и т.п. — только с контекстом принтера
    if re.search(r"\bkobra\b", tl) and re.search(r"\b(s1|s2|go|max|neo|plus|combo|pro)\b", tl):
        return True
    if re.search(r"\bphoton\b", tl) and re.search(r"\b(m3|m5|mono|ultra|x6)\b", tl):
        return True
    return False


def _ace_mentioned(text: str) -> bool:
    t = text.lower()
    return bool(
        any(
            k in t
            for k in (
                "ace pro",
                "ace-pro",
                "аська",
                "аска",
                "аськ",
                "эйс",
            )
        )
        or re.search(r"\bace\b", t)
    )


def _mentions_competitor_printer(text: str) -> bool:
    """Bambu, P2S и др. — не путать с Anycubic Kobra в вики."""
    if not text:
        return False
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return bool(
        re.search(
            r"\b(?:"
            r"bambu|бамбук|п2с|p2s|x1c|"
            r"prusa|пруса|"
            r"creality|кр[еи]ал[иы]?т[иы]|ender|"
            r"flashforge|flashforg|"
            r"raise3d|qidi"
            r")\b",
            t,
        )
    )


def _model_slug_hints(text: str) -> frozenset[str]:
    """Подстроки пути вики (латиница), по которым отличают линейки принтеров."""
    out: set[str] = set()
    tl = text.lower()
    combo = "combo" in tl or "комбо" in tl
    # Kobra 3 Max — до ветки «Kobra 3», иначе спутать с обычной тройкой
    is_kobra_3_max = bool(re.search(r"kobra\s*3\s*max\b", tl) or "kobra-3-max" in tl)
    if is_kobra_3_max:
        if combo:
            out.add("kobra-max-combo")
            out.add("kobra-max")
        else:
            out.add("kobra-max")
    elif re.search(r"kobra\s*max\b", tl) or "kobra-max" in tl:
        if combo:
            out.add("kobra-max-combo")
            out.add("kobra-max")
        else:
            out.add("kobra-max")

    is_kobra_s1 = bool(
        re.search(r"kobra\s*s\s*1\b", tl)
        or re.search(r"kobra\s*s1\b", tl)
        or "kobra-s1" in tl
        or re.search(r"кобра\s*s\s*1\b", tl)
        or re.search(r"кобра\s*s1\b", tl)
    )
    if is_kobra_s1:
        if combo or "kobra-s1-combo" in tl or "комбо" in tl:
            out.add("kobra-s1-combo")
            out.add("kobra-s1")  # тот же корпус; путь вики часто с суффиксом -combo
        else:
            out.add("kobra-s1")
            # Большинство гайдов S1 (подача, заторы) лежат в ветке -combo.
            out.add("kobra-s1-combo")

    if (re.search(r"kobra\s*3\b", tl) or "kobra-3" in tl or re.search(r"кобра\s*3\b", tl)) and not is_kobra_3_max:
        if combo or "kobra-3-combo" in tl:
            out.add("kobra-3-combo")
            out.add("kobra-3")
        else:
            out.add("kobra-3")

    if re.search(r"kobra\s*2\b", tl) or "kobra-2" in tl or re.search(r"кобра\s*2\b", tl):
        out.add("kobra-2")

    if re.search(r"kobra\s*go\b", tl) or "kobra-go" in tl:
        out.add("kobra-go")

    if re.search(r"kobra\s*neo\b", tl) or "kobra-neo" in tl:
        out.add("kobra-neo")

    if re.search(r"\bvyper\b", tl):
        out.add("vyper")

    if re.search(r"\bchiron\b", tl):
        out.add("chiron")

    if re.search(r"\bphoton\b", tl):
        out.add("photon")

    return frozenset(out)


def _extract_error_code(text: str) -> str | None:
    """
    Возвращает числовой код ошибки (4–7 цифр), если он явно присутствует в тексте.

    Формат на вики обычно: /error-codes/<code>-code/...

    """
    m = re.search(r"\b(\d{4,7})\b", text.lower())
    return m.group(1) if m else None


def _is_error_code_query(text: str) -> bool:
    """
    Сообщение, где ключевой смысл — код ошибки (например "ошибка 11407").

    """
    code = _extract_error_code(text)
    if not code:
        return False
    t = text.lower()
    # если рядом есть явная "ошибка/err/error" — точно запрос по коду
    return any(k in t for k in ("ошибк", "error", "err"))


def _has_geo_social_cues(text: str) -> bool:
    """Просьба найти владельцев принтера поблизости (не тех. вопрос)."""
    t = text.lower()
    people = ("кто", "есть ли", "найдётся", "найдется", "познаком", "встрет", "живёт", "живет", "живут")
    geo = (
        "рядом",
        "поблизости",
        "недалеко",
        "област",
        "город",
        "обнинск",
        "наро-фоминск",
        "наро фоминск",
        "москв",
        "питер",
        "спб",
        "санкт-петербург",
        "район",
    )
    return any(p in t for p in people) and any(g in t for g in geo)


def _user_already_replaced_motherboard(text: str) -> bool:
    t = text.lower()
    if not any(k in t for k in ("материн", "motherboard", "mainboard", "main board")):
        return False
    return any(
        k in t
        for k in (
            "поменял",
            "заменил",
            "сменил",
            "прислали",
            "поставил",
            "менял",
            "replaced",
            "already",
        )
    )
