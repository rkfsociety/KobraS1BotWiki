"""Разбор кодов ошибок: поиск и выбор страниц вики по коду."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.web_wiki_index import WebWikiDoc, WebWikiIndex

from app.bot.heuristics._base import _model_slug_hints


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
