"""Ранжирование результатов поиска по вики (бонусы/штрафы по URL)."""
from __future__ import annotations

import re

from telegram.ext import ContextTypes

from app.bot.stores import _preferred_fix_url
from app.bot.text_heuristics import (
    _extract_error_code,
    _is_error_code_query,
    _model_slug_hints,
)
from app.web_wiki_index import WebWikiDoc, WebWikiIndex

def _url_model_bonus(url: str, hints: frozenset[str]) -> int:
    if not hints:
        return 0
    u = url.lower()
    hits = sum(1 for h in hints if h in u)
    return min(78, hits * 40)


def _topic_path_bonus(topic: str | None, url: str) -> int:
    """Слегка подталкиваем URL под формулировку исходного вопроса (только уточнение по модели)."""
    if not topic:
        return 0
    tl = topic.lower()
    u = url.lower()
    b = 0
    # Коды ошибок: предпочитаем раздел /error-codes/ и не уходим в FAQ.
    if re.search(r"\b1\d{4}\b", tl):
        if "/error-codes/" in u:
            b += 70
        if "/faq" in u or u.rstrip("/").endswith("/faq"):
            b -= 55
    if "экструдер" in tl or "extruder" in tl:
        if "extruder" in u:
            b += 24
        if "print-head" in u and "extruder" not in u:
            b -= 20
    if "сопло" in tl or "nozzle" in tl:
        if "nozzle" in u:
            b += 20
    if "хотэнд" in tl or "hotend" in tl or "hot end" in tl:
        if "hotend" in u or "hot-end" in u:
            b += 20
    if "двер" in tl or "door" in tl or "петл" in tl or "hinge" in tl:
        if "glass-door" in u:
            b += 52
        elif "door" in u and "glass" in u:
            b += 28
    if _topic_is_bed_setup_intent(topic):
        if "nozzle-scraping" in u or "scraping" in u:
            b += 55
        elif "first-layer" in u:
            b += 28
        elif "leveling" in u or "level" in u:
            b += 18
        if "hot-bed" in u or "hotbed" in u:
            b += 12
    return b


def _topic_is_bed_setup_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    has_bed = any(k in tl for k in ("стол", "bed", "платформ", "hot bed", "hotbed"))
    has_setup = any(
        k in tl
        for k in (
            "настрой",
            "калибр",
            "уровн",
            "level",
            "calibrat",
            "куб",
            "scraping",
            "царапа",
            "первый слой",
            "first layer",
        )
    )
    return has_bed and has_setup


def _topic_is_door_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    return any(k in tl for k in ("двер", "door", "петл", "hinge", "enclosure", "glass door"))


def _topic_is_nozzle_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    return any(k in tl for k in ("сопло", "nozzle"))


def _topic_is_nozzle_silicone_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    return any(
        k in tl
        for k in (
            "силикон",
            "втулк",
            "носок",
            "чехол",
            "silicone",
            "sock",
        )
    )


def _nozzle_guide_url_plausible(url: str, *, allow_silicone: bool) -> bool:
    """
    Если спросили «как поменять сопло», не нужно отдавать гайды про silicone sock/sleeve.
    """
    u = url.lower().replace("_", "-")
    if "nozzle" not in u:
        return False
    # если это явно про силиконовую втулку/носок — только когда пользователь просил именно это
    if ("silicone" in u or "sock" in u) and not allow_silicone:
        return False
    # стараемся требовать "replacement/replace" для "поменять/заменить"
    if any(k in u for k in ("replacement", "replace")):
        return True
    # иногда страницы названы странно, но всё равно про сопло — пропускаем, если хоть явно nozzle и guide
    if "guide" in u:
        return True
    return True


def _wrong_part_for_topic_penalty(topic: str | None, url: str) -> int:
    """Тема «дверь», а URL про другое узло — сильный штраф (иначе тянет purge-wiper из-за replace)."""
    if not _topic_is_door_intent(topic):
        return 0
    u = url.lower().replace("_", "-")
    if "glass-door" in u or ("glass" in u and "door" in u):
        return 0
    bad = (
        "wiper",
        "purge",
        "filament",
        "extruder",
        "nozzle",
        "hotend",
        "motor",
        "belt",
        "power-supply",
        "psu",
        "heated-bed",
        "heatbed",
        "bed-replacement",
        "firmware",
        "thermistor",
        "print-head",
    )
    for b in bad:
        if b in u:
            return 78
    return 0


def _guide_url_matches_model_hints(url: str, hints: frozenset[str]) -> bool:
    """Если пользователь назвал модель — в ссылке должен быть тот же slug (иначе гайда «для неё» нет)."""
    # Для кодов ошибок модель часто кодируется иначе (/s1, /kobra-3 и т.п.),
    # поэтому жёсткое совпадение slug ломает выдачу. Разрешаем /error-codes/ всегда.
    if "/error-codes/" in url.lower():
        return True
    if not hints:
        return True
    u = url.lower()
    return any(h in u for h in hints)


def _door_guide_url_plausible(url: str) -> bool:
    u = url.lower().replace("_", "-")
    if "glass-door" in u:
        return True
    if "door" in u and ("glass" in u or "hinge" in u or "cover" in u):
        return True
    return False


def _response_wiki_url_acceptable(question: str, url: str) -> bool:
    """Не слать ссылку, если модель в URL не та или тема (например дверь) явно не совпадает со slug статьи."""
    # Для запросов по коду ошибки отдаём только точные страницы /error-codes/<code>-code...
    code = _extract_error_code(question)
    if code and _is_error_code_query(question):
        u = url.lower()
        if "/error-codes/" not in u:
            return False
        # Не отдаём общий раздел /error-codes — только страницу конкретного кода.
        if f"/{code}-code" not in u:
            return False
    else:
        # Если это НЕ запрос по коду ошибки — не отдаём раздел /error-codes вообще,
        # иначе фразы типа "ошибка природы, помогите" тянут туда.
        if "/error-codes" in url.lower():
            return False
    if not _guide_url_matches_model_hints(url, _model_slug_hints(question)):
        return False
    if _topic_is_door_intent(question) and not _door_guide_url_plausible(url):
        return False
    if _topic_is_nozzle_intent(question) and not _nozzle_guide_url_plausible(
        url, allow_silicone=_topic_is_nozzle_silicone_intent(question)
    ):
        return False
    return True

def _url_model_penalty(url: str, hints: frozenset[str], topic: str | None = None) -> int:
    """Если модель в запросе ясна, но URL явно про другую линейку — сильный штраф."""
    u = url.lower()
    if not hints:
        return 0
    if any(h in u for h in hints):
        return 0
    pen = 0
    siblings: dict[str, tuple[str, ...]] = {
        "kobra-3": ("kobra-s1", "kobra-2", "vyper", "chiron"),
        "kobra-3-combo": ("kobra-s1", "kobra-2", "vyper", "chiron"),
        "kobra-s1": ("kobra-3", "kobra-2", "vyper", "chiron"),
        "kobra-s1-combo": ("kobra-3", "kobra-2", "vyper", "chiron"),
        "kobra-2": ("kobra-s1", "kobra-3", "vyper", "chiron"),
        "kobra-max": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "kobra-max-combo": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "kobra-go": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "kobra-neo": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "vyper": ("kobra-s1", "kobra-3", "kobra-2"),
        "chiron": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
    }
    for h in hints:
        for bad in siblings.get(h, ()):
            if bad in u:
                pen = max(pen, 65)
    return pen


def _search_best_with_model_bias(
    index: WebWikiIndex,
    variants: list[str],
    *,
    context_text: str,
    topic_for_keywords: str | None = None,
    top_k: int = 28,
) -> tuple[WebWikiDoc | None, int]:
    """
    Поиск по вариантам запроса с учётом явной модели в context_text (бонус/штраф по URL).
    Итоговый score для порогов — в диапазоне 0..100, но победитель выбирается по «сырым» баллам до cap.
    """
    hints = _model_slug_hints(context_text)
    by_url: dict[str, tuple[WebWikiDoc, int]] = {}
    for q in variants:
        q = (q or "").strip()
        if not q:
            continue
        for doc, score in index.search(q, top_k=top_k):
            bonus = _url_model_bonus(doc.url, hints)
            penalty = _url_model_penalty(doc.url, hints, topic_for_keywords)
            kw = _topic_path_bonus(topic_for_keywords, doc.url)
            part_pen = _wrong_part_for_topic_penalty(topic_for_keywords, doc.url)
            adj_raw = int(score) + bonus - penalty + kw - part_pen
            prev = by_url.get(doc.url)
            if prev is None or adj_raw > prev[1]:
                by_url[doc.url] = (doc, adj_raw)
    if not by_url:
        return None, -1
    best_doc, raw_best = max(by_url.values(), key=lambda x: x[1])
    capped = max(0, min(100, raw_best))
    return best_doc, capped

def _search_best_with_model_bias_excluding(
    index: WebWikiIndex,
    variants: list[str],
    *,
    context: ContextTypes.DEFAULT_TYPE,
    context_text: str,
    topic_for_keywords: str | None,
    exclude_urls: set[str],
    top_k: int = 28,
) -> tuple[WebWikiDoc | None, int]:
    # Если есть "правильная" ссылка, заданная через /fix — используем её.
    preferred = _preferred_fix_url(context=context, query=context_text)
    if preferred:
        for d in getattr(index, "_docs", []):  # type: ignore[attr-defined]
            if getattr(d, "url", None) == preferred:
                return d, 100
    doc, score = _search_best_with_model_bias(
        index,
        variants,
        context_text=context_text,
        topic_for_keywords=topic_for_keywords,
        top_k=top_k,
    )
    if not doc:
        return None, score
    if doc.url in exclude_urls:
        # попробуем найти следующий — делаем "ручной" проход без exclude
        hints = _model_slug_hints(context_text)
        by_url: dict[str, tuple[WebWikiDoc, int]] = {}
        for q in variants:
            q = (q or "").strip()
            if not q:
                continue
            for d2, sc in index.search(q, top_k=top_k):
                if d2.url in exclude_urls:
                    continue
                bonus = _url_model_bonus(d2.url, hints)
                penalty = _url_model_penalty(d2.url, hints, topic_for_keywords)
                kw = _topic_path_bonus(topic_for_keywords, d2.url)
                part_pen = _wrong_part_for_topic_penalty(topic_for_keywords, d2.url)
                adj_raw = int(sc) + bonus - penalty + kw - part_pen
                prev = by_url.get(d2.url)
                if prev is None or adj_raw > prev[1]:
                    by_url[d2.url] = (d2, adj_raw)
        if not by_url:
            return None, -1
        best_doc2, raw_best = max(by_url.values(), key=lambda x: x[1])
        capped = max(0, min(100, raw_best))
        return best_doc2, capped
    return doc, score
