"""Слой/печать/тест и уточнение модели (кобра ≠ Kobra S1)."""
from __future__ import annotations

import re

from app.bot.text_heuristics import (
    _is_error_code_query,
    _model_slug_hints,
    _topic_is_ace_connection_intent,
    _topic_is_ace_not_detected_intent,
)


def model_specifically_identified(text: str) -> bool:
    # Конкретная модель (S1, Kobra 2, …), а не только «кобра» / Anycubic
    return bool(_model_slug_hints(text))


def topic_is_layer_slicing_intent(text: str | None) -> bool:
    if not text:
        return False
    from app.bot.text_heuristics import (
        _is_non_wiki_chatter_message,
        _topic_is_filament_slicing_settings_intent,
    )

    if _is_non_wiki_chatter_message(text):
        return False
    # PETG/TPU + мост/поддержки в нарезке — общая вики по материалам, не модель Kobra.
    if _topic_is_filament_slicing_settings_intent(text):
        return False
    tl = text.lower()
    if re.search(r"\b0\.\d{1,3}\b", tl) and re.search(r"слой|слоя|слое|слою|layer", tl):
        return True
    if re.search(r"\bслайс(?!er\w*)\b", tl) or re.search(r"\bslic(?!er\w*)\b", tl):
        return True
    if re.search(r"\b(?:тестов(?:ую|ый|ая)|тест)\s*(?:печат|принт|print)\b", tl):
        return True
    if re.search(r"\btest\s*print\b|\bbenchy\b", tl):
        return True
    if re.search(r"\bтест\b", tl) and re.search(r"\b(?:слой|слоя|слое|layer|0\.\d|калибр|level)\b", tl):
        return True
    # Голое «слой» в настройках печати — не «послойно» в обсуждении прочности пластика.
    if re.search(r"\b(?:слой|слоя|слое|слою|layer)\w*\b", tl):
        return True
    if re.search(r"\b(?:печать|в\s+печать|print)\b", tl) and re.search(
        r"\b(?:слой|слоя|слое|профил|слайс|калибр|benchy|level|уровн|0\.\d|тест)\b",
        tl,
    ):
        return True
    if re.search(r"\bпрофил\w*\b", tl) and re.search(r"\b(?:сопл|nozzle|слой|layer|слайс)\b", tl):
        return True
    return False


def topic_requires_printer_model(text: str) -> bool:
    from app.bot.text_heuristics import _topic_needs_printer_model

    return _topic_needs_printer_model(text) or topic_is_layer_slicing_intent(text)


def needs_model_clarification_for(text: str) -> bool:
    if _is_error_code_query(text):
        return False
    from app.bot.text_heuristics import _is_non_wiki_chatter_message

    if _is_non_wiki_chatter_message(text):
        return False
    return topic_requires_printer_model(text) and not model_specifically_identified(text)


def is_wiki_model_overview_url(url: str) -> bool:
    u = url.lower().split("?")[0].rstrip("/")
    return bool(re.search(r"/fdm-3d-printer/[^/]+$", u))


def overview_url_penalty(topic: str | None, url: str) -> int:
    if not topic or not is_wiki_model_overview_url(url):
        return 0
    if topic_requires_printer_model(topic) or topic_is_layer_slicing_intent(topic):
        return 72
    return 0


def wiki_url_acceptable_for_topic(question: str, url: str) -> bool:
    if (
        topic_requires_printer_model(question)
        and not model_specifically_identified(question)
        and not _topic_is_ace_connection_intent(question)
        and not _topic_is_ace_not_detected_intent(question)
    ):
        return False
    if (topic_requires_printer_model(question) or topic_is_layer_slicing_intent(question)) and is_wiki_model_overview_url(
        url
    ):
        return False
    return True


def response_wiki_url_acceptable(question: str, url: str) -> bool:
    """Проверка URL: сначала модель/обзор, затем штатные правила wiki_ranking."""
    if not wiki_url_acceptable_for_topic(question, url):
        return False
    from app.bot.wiki_ranking import _response_wiki_url_acceptable as base_ok

    return base_ok(question, url)


def apply_runtime_patches() -> None:
    """Подмена проверок в уже импортируемых модулях (до handlers)."""
    import app.bot.text_heuristics as text_heuristics
    import app.bot.wiki_ranking as wiki_ranking
    import app.ru_layer as ru_layer

    text_heuristics._needs_model_clarification = needs_model_clarification_for

    base_url_ok = wiki_ranking._response_wiki_url_acceptable

    def _patched_response_wiki_url_acceptable(question: str, url: str) -> bool:
        if not wiki_url_acceptable_for_topic(question, url):
            return False
        return base_url_ok(question, url)

    wiki_ranking._response_wiki_url_acceptable = _patched_response_wiki_url_acceptable

    ru_extra: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bслой\w*\b", re.I), "layer height"),
        (re.compile(r"\b0\.\d{1,3}\s*(?:мм|mm)?\b", re.I), "layer height mm"),
        (re.compile(r"\bпечать\b|\bв\s+печать\b", re.I), "printing print"),
        (re.compile(r"\bтест\w*\b", re.I), "test print calibration"),
        (re.compile(r"\bслайс\w*\b", re.I), "slicer slicing"),
    ]
    ru_layer._MAP[:0] = ru_extra


apply_runtime_patches()
