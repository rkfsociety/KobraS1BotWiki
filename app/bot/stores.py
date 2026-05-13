"""Локальные сторы (JSON) и нормализация запросов."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from telegram.ext import ContextTypes

from app.bot.constants import (
    ANSWER_CTX_STORE,
    CLARIFY_STORE,
    FEEDBACK_STORE,
    FIX_STORE,
)

def _clarify_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _load_clarify_store() -> dict[str, dict]:
    try:
        if not CLARIFY_STORE.exists():
            return {}
        raw = json.loads(CLARIFY_STORE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_clarify_store(data: dict[str, dict]) -> None:
    CLARIFY_STORE.parent.mkdir(parents=True, exist_ok=True)
    CLARIFY_STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def _load_answer_ctx_store() -> dict[str, dict]:
    try:
        if not ANSWER_CTX_STORE.exists():
            return {}
        raw = json.loads(ANSWER_CTX_STORE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_answer_ctx_store(data: dict[str, dict]) -> None:
    ANSWER_CTX_STORE.parent.mkdir(parents=True, exist_ok=True)
    ANSWER_CTX_STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _answer_ctx_key(chat_id: int, bot_message_id: int) -> str:
    return f"{chat_id}:{bot_message_id}"


def _record_bot_answer_context(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    bot_message_id: int,
    query: str,
    url: str | None,
) -> None:
    """
    Запоминаем, на какой запрос бот ответил данным сообщением.
    Нужно для команды /error (перепоиск и "обучение").
    """
    store = context.application.bot_data.setdefault("answer_ctx_store", {})
    if not isinstance(store, dict):
        store = {}
        context.application.bot_data["answer_ctx_store"] = store

    store[_answer_ctx_key(chat_id, bot_message_id)] = {
        "q": query,
        "url": url,
        "ts": time.time(),
    }
    # Ограничим размер, чтобы не разрасталось бесконечно
    if len(store) > 800:
        # удаляем самые старые
        items = sorted(store.items(), key=lambda kv: float(kv[1].get("ts", 0.0)))
        for k, _ in items[:200]:
            store.pop(k, None)
    _save_answer_ctx_store(store)


def _load_feedback_store() -> dict[str, list[str]]:
    """
    query_norm -> [bad_url, ...]
    """
    try:
        if not FEEDBACK_STORE.exists():
            return {}
        raw = json.loads(FEEDBACK_STORE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, list):
                out[k] = [str(x) for x in v if isinstance(x, str)]
        return out
    except Exception:
        return {}


def _save_feedback_store(data: dict[str, list[str]]) -> None:
    FEEDBACK_STORE.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _remember_bad_answer(*, context: ContextTypes.DEFAULT_TYPE, query: str, bad_url: str | None) -> None:
    if not bad_url:
        return
    qn = _norm_text(query)
    fb = context.application.bot_data.setdefault("feedback_store", {})
    if not isinstance(fb, dict):
        fb = {}
        context.application.bot_data["feedback_store"] = fb
    lst = fb.get(qn)
    if not isinstance(lst, list):
        lst = []
    if bad_url not in lst:
        lst.append(bad_url)
    # ограничим на запрос
    fb[qn] = lst[-20:]
    _save_feedback_store(fb)


def _excluded_urls_for_query(*, context: ContextTypes.DEFAULT_TYPE, query: str) -> set[str]:
    fb = context.application.bot_data.get("feedback_store", {})
    if not isinstance(fb, dict):
        return set()
    lst = fb.get(_norm_text(query), [])
    if not isinstance(lst, list):
        return set()
    return {str(x) for x in lst if isinstance(x, str)}


def _load_fix_store() -> dict[str, str]:
    """
    query_norm -> good_url
    """
    try:
        if not FIX_STORE.exists():
            return {}
        raw = json.loads(FIX_STORE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                out[k] = v.strip()
        return out
    except Exception:
        return {}


def _save_fix_store(data: dict[str, str]) -> None:
    FIX_STORE.parent.mkdir(parents=True, exist_ok=True)
    FIX_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _remember_good_fix(*, context: ContextTypes.DEFAULT_TYPE, query: str, good_url: str) -> None:
    qn = _norm_text(query)
    fixes = context.application.bot_data.setdefault("fix_store", {})
    if not isinstance(fixes, dict):
        fixes = {}
        context.application.bot_data["fix_store"] = fixes
    fixes[qn] = good_url
    # ограничим размер
    if len(fixes) > 800:
        # не знаем ts, поэтому просто обрежем по ключам
        for k in sorted(fixes.keys())[:200]:
            fixes.pop(k, None)
    _save_fix_store(fixes)


def _preferred_fix_url(*, context: ContextTypes.DEFAULT_TYPE, query: str) -> str | None:
    fixes = context.application.bot_data.get("fix_store", {})
    if not isinstance(fixes, dict):
        return None
    return fixes.get(_norm_text(query))

