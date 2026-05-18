"""Эвристики по тексту вопроса (модель, тема, код ошибки)."""
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


def _topic_needs_printer_model(text: str) -> bool:
    """Тема вопроса обычно специфична для модели (без модели ответ легко промахнется)."""
    t = text.lower()
    ru = (
        "экструдер",
        "сопло",
        "хотэнд",
        "прошив",
        # "ошибка" слишком общее слово (напр. "ошибка природы") — модель по нему не уточняем.
        # Коды ошибок обрабатываются отдельно через _extract_error_code/_is_error_code_query.
        "калибр",
        "левел",
        "уровн",
        "настрой",
        "не печатает",
        "ремень",
        "застрял",
        "заклинил",
        "стол",
        "подогрев",
        "сопл",
        "двер",
        "петл",
        "стекл",
    )
    en = (
        "extruder",
        "nozzle",
        "hotend",
        "hot end",
        "firmware",
        "calibrat",
        "leveling",
        "level ",
        " bed",
        "heated bed",
        "build plate",
        "belt",
        "jam",
        "clog",
        "stepper",
        "door",
        "glass door",
        "hinge",
        "enclosure",
    )
    if any(x in t for x in ru + en):
        return True
    # «кубы» / leveling cubes при настройке стола — разная инструкция по моделям
    if "куб" in t and any(
        k in t for k in ("стол", "калибр", "уровн", "настрой", "level", "bed", "скрейп", "царап", "сопл")
    ):
        return True
    return False


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


def _error_code_variant_suffix(code: str, url: str) -> str | None:
    """
    /en/error-codes/<code>-code/<suffix> -> suffix
    /en/error-codes/<code>-code -> None
    """
    u = (url or "").lower().rstrip("/")
    base = f"/error-codes/{code}-code"
    if base not in u:
        return None
    after = u.split(base, 1)[1]
    if not after:
        return None
    after = after.lstrip("/")
    if not after:
        return None
    return after.split("/", 1)[0] or None


def _error_code_target_suffix(text: str) -> str | None:
    """
    Пытаемся понять, для какой линейки нужна страница кода ошибки.
    Поддерживаем явные сокращения (s1/k3/k3m) и названия моделей (через hints).
    """
    tl = text.lower()
    # явные сокращения
    if re.search(r"\bk3m\b", tl):
        return "k3m"
    if re.search(r"\bk3\b", tl) or re.search(r"\bkobra\s*3\b", tl) or "kobra-3" in tl:
        return "k3"
    if re.search(r"\bs1\b", tl) or "kobra-s1" in tl or re.search(r"kobra\s*s\s*1\b", tl):
        return "s1"

    hints = _model_slug_hints(text)
    if "kobra-s1" in hints or "kobra-s1-combo" in hints:
        return "s1"
    if "kobra-3" in hints or "kobra-3-combo" in hints:
        return "k3"
    if "kobra-max" in hints or "kobra-max-combo" in hints:
        return "k3m"
    return None


def _error_code_candidates(index: WebWikiIndex, code: str) -> list[WebWikiDoc]:
    target = f"/error-codes/{code}-code"
    out: list[WebWikiDoc] = []
    for d in getattr(index, "_docs", []):  # type: ignore[attr-defined]
        try:
            u = (d.url or "").lower()
        except Exception:
            continue
        if target in u:
            out.append(d)
    return out


def _pick_error_code_doc(index: WebWikiIndex, code: str, *, context_text: str) -> WebWikiDoc | None:
    """
    Для кодов ошибок не используем fuzzy-поиск (он может путать коды).
    Ищем только страницы вида /error-codes/<code>-code...
    """
    candidates = _error_code_candidates(index, code)
    if not candidates:
        return None
    # Если вариантов несколько — пытаемся выбрать по модели из текста.
    target_suffix = _error_code_target_suffix(context_text)
    if target_suffix:
        for d in candidates:
            if _error_code_variant_suffix(code, d.url) == target_suffix:
                return d
    # Предпочитаем базовую страницу кода без суффиксов (/s1, /k3, и т.п.)
    base = f"https://wiki.anycubic.com/en/error-codes/{code}-code"
    for d in candidates:
        if d.url.rstrip("/") == base:
            return d
    # Если суффикса не нашли и базовой нет — неоднозначно, пусть вызывающий уточнит модель.
    return candidates[0] if len(candidates) == 1 else None

def _topic_is_ace_not_detected_intent(text: str) -> bool:
    """Принтер/софт не видит ACE Pro (аська)."""
    t = text.lower()
    has_ace = any(
        k in t
        for k in (
            "ace pro",
            "ace-pro",
            "аська",
            "аска",
            "аськ",
            "эйс",
        )
    ) or re.search(r"\bace\b", t)
    has_not_seen = any(
        k in t
        for k in (
            "не видит",
            "не вид",
            "не определя",
            "не наход",
            "не подключа",
            "not detected",
            "doesn't see",
            "does not see",
            "not see",
            "can't see",
            "cannot see",
        )
    ) or ("видится" in t and any(k in t for k in ("аська", "аска", "ace")))
    return bool(has_ace and has_not_seen)


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


def _is_geo_social_only_request(text: str) -> bool:
    """
    Координация встреч/обмена с соседями — бот молчит.
    Если в том же сообщении есть тех. проблема (ACE, код ошибки) — ищем вики.
    """
    if not _has_geo_social_cues(text):
        return False
    if _topic_is_ace_not_detected_intent(text) or _is_error_code_query(text):
        return False
    if _topic_needs_printer_model(text) and _printer_mentioned(text):
        return False
    return True


def _needs_model_clarification(text: str) -> bool:
    # Для кодов ошибок модель не спрашиваем — либо найдём страницу по коду, либо промолчим.
    if _is_error_code_query(text):
        return False
    return _topic_needs_printer_model(text) and not _printer_mentioned(text)


def _is_generic_help_without_context(text: str) -> bool:
    """
    "помогите/спасите" без конкретики — лучше попросить уточнение, а не искать по вики наугад.
    """
    t = (text or "").lower()
    if not any(k in t for k in ("помогите", "спасите", "help", "памагити", "спаситипамагити")):
        return False
    # если есть код ошибки или модель/принтер или тех. тема — это уже конкретика
    if _is_error_code_query(text) or _printer_mentioned(text) or _topic_needs_printer_model(text):
        return False
    return True


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


def _topic_is_filament_feed_intent(text: str | None) -> bool:
    """
    Подача филамента / экструдер крутит, но не тянет, срывы шестерни, затор.
    Не путать с осью Z/X/Y и USB-драйверами.
    """
    if not text:
        return False
    tl = text.lower()
    has_filament = any(
        k in tl
        for k in (
            "филамент",
            "filament",
            "подач",
            "feeding",
            "feed ",
            "экструдер",
            "extruder",
            "шестерн",
            "gear",
            "ролик",
            "idler",
        )
    )
    has_problem = any(
        k in tl
        for k in (
            "не пода",
            "не тян",
            "не идёт",
            "не идет",
            "перестал",
            "срыв",
            "slip",
            "skipping",
            "застрял",
            "jam",
            "clog",
            "затор",
            "block",
            "не крут",
        )
    )
    has_feed_motor = ("мотор" in tl or "motor" in tl or "шагов" in tl or "stepper" in tl) and any(
        k in tl
        for k in (
            "подач",
            "филамент",
            "экструдер",
            "feed",
            "extruder",
            "шестерн",
            "filament",
        )
    )
    return (has_filament and has_problem) or has_feed_motor
