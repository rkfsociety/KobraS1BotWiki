"""Локальные сторы (JSON) и нормализация запросов."""
from __future__ import annotations

import json
import math
import re
import tempfile
import threading
import time
from pathlib import Path
from functools import lru_cache
from heapq import nlargest, nsmallest
from typing import Any

from telegram.ext import ContextTypes

from app.bot.constants import (
    ANSWER_CTX_STORE,
    CLARIFY_STORE,
    FEEDBACK_STORE,
    FIX_STORE,
)

_STORE_SAVE_LOCK = threading.Lock()
_ANSWER_CTX_SAVE_INTERVAL = 60.0
_MAX_ANSWER_CTX_ENTRIES = 800
_MAX_CLARIFY_ENTRIES = 1024
_MAX_FIX_ENTRIES = 800
_MAX_FEEDBACK_ENTRIES = 2000


def _save_interval_elapsed(last_value: object, *, now: float, interval: float) -> bool:
    """Проверяет интервал записи и безопасно обрабатывает повреждённый timestamp."""
    try:
        last = float(last_value)
    except (TypeError, ValueError, OverflowError):
        return True
    return not math.isfinite(last) or now - last >= interval


def _save_json_atomic(path: Path, data: object, *, indent: int | None = None) -> None:
    """Атомарно сохраняет JSON, не оставляя рабочий файл частично записанным."""
    payload = json.dumps(data, ensure_ascii=False, indent=indent)
    with _STORE_SAVE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(payload)
                temporary_path = Path(temporary.name)
            temporary_path.replace(path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

def _clarify_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _clarify_timestamp(entry: object) -> float:
    if not isinstance(entry, dict):
        return 0.0
    try:
        value = float(entry.get("ts", 0.0) or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _bound_clarify_store(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    valid = {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    if len(valid) <= _MAX_CLARIFY_ENTRIES and len(valid) == len(raw):
        return raw
    if len(valid) <= _MAX_CLARIFY_ENTRIES:
        return valid
    return dict(
        nlargest(
            _MAX_CLARIFY_ENTRIES,
            valid.items(),
            key=lambda item: _clarify_timestamp(item[1]),
        )
    )


def _load_clarify_store() -> dict[str, dict]:
    try:
        if not CLARIFY_STORE.exists():
            return {}
        raw = json.loads(CLARIFY_STORE.read_text(encoding="utf-8"))
        return _bound_clarify_store(raw)
    except Exception:
        return {}


def _save_clarify_store(data: dict[str, dict]) -> None:
    _save_json_atomic(CLARIFY_STORE, _bound_clarify_store(data))

@lru_cache(maxsize=4096)
def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()

def _bound_answer_ctx_store(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    valid = {
        key: value
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    if len(valid) <= _MAX_ANSWER_CTX_ENTRIES and len(valid) == len(raw):
        return raw
    if len(valid) <= _MAX_ANSWER_CTX_ENTRIES:
        return valid
    return dict(
        nlargest(
            _MAX_ANSWER_CTX_ENTRIES,
            valid.items(),
            key=lambda item: _answer_ctx_timestamp(item[1]),
        )
    )


def _load_answer_ctx_store() -> dict[str, dict]:
    try:
        if not ANSWER_CTX_STORE.exists():
            return {}
        raw = json.loads(ANSWER_CTX_STORE.read_text(encoding="utf-8"))
        return _bound_answer_ctx_store(raw)
    except Exception:
        return {}


def _get_answer_ctx_store(bot_data: dict[str, Any]) -> dict[str, dict]:
    """Возвращает store из памяти и читает диск только при первом обращении."""
    store = bot_data.get("answer_ctx_store")
    if isinstance(store, dict):
        bounded = _bound_answer_ctx_store(store)
        if bounded is not store:
            bot_data["answer_ctx_store"] = bounded
            store = bounded
        return store
    store = _load_answer_ctx_store()
    bot_data["answer_ctx_store"] = store
    return store


def _save_answer_ctx_store(
    data: dict[str, dict], *, bot_data: dict[str, Any] | None = None, force: bool = False
) -> None:
    now = time.time()
    if not force and bot_data is not None:
        if not _save_interval_elapsed(
            bot_data.get("_answer_ctx_last_save", 0.0),
            now=now,
            interval=_ANSWER_CTX_SAVE_INTERVAL,
        ):
            return
    _save_json_atomic(ANSWER_CTX_STORE, data)
    if bot_data is not None:
        bot_data["_answer_ctx_last_save"] = now


def flush_answer_ctx_store(bot_data: dict[str, Any]) -> None:
    """Принудительно сохраняет контекст ответов перед остановкой процесса."""
    store = bot_data.get("answer_ctx_store")
    if isinstance(store, dict):
        _save_answer_ctx_store(store, bot_data=bot_data, force=True)


def _answer_ctx_key(chat_id: int, bot_message_id: int) -> str:
    return f"{chat_id}:{bot_message_id}"


def _answer_ctx_timestamp(entry: object) -> float:
    if not isinstance(entry, dict):
        return 0.0
    try:
        value = float(entry.get("ts", 0.0) or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) else 0.0


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
    store = _get_answer_ctx_store(context.application.bot_data)

    store[_answer_ctx_key(chat_id, bot_message_id)] = {
        "q": query,
        "url": url,
        "ts": time.time(),
    }
    # Ограничим размер, чтобы не разрасталось бесконечно
    if len(store) > _MAX_ANSWER_CTX_ENTRIES:
        # удаляем самые старые, не сортируя весь store
        items = nsmallest(
            len(store) - (_MAX_ANSWER_CTX_ENTRIES - 200),
            store.items(),
            key=lambda item: _answer_ctx_timestamp(item[1]),
        )
        for k, _ in items:
            store.pop(k, None)
    _save_answer_ctx_store(store, bot_data=context.application.bot_data)


def _bound_feedback_store(raw: object) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    valid: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        valid[key] = [item for item in value if isinstance(item, str)][-20:]
    if len(valid) <= _MAX_FEEDBACK_ENTRIES:
        return valid
    return dict(list(valid.items())[-_MAX_FEEDBACK_ENTRIES:])


def _load_feedback_store() -> dict[str, list[str]]:
    """
    query_norm -> [bad_url, ...]
    """
    try:
        if not FEEDBACK_STORE.exists():
            return {}
        raw = json.loads(FEEDBACK_STORE.read_text(encoding="utf-8"))
        return _bound_feedback_store(raw)
    except Exception:
        return {}


def _save_feedback_store(data: dict[str, list[str]]) -> None:
    _save_json_atomic(FEEDBACK_STORE, _bound_feedback_store(data), indent=2)


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
    if len(fb) > _MAX_FEEDBACK_ENTRIES:
        fb = _bound_feedback_store(fb)
        context.application.bot_data["feedback_store"] = fb
    _save_feedback_store(fb)


def _excluded_urls_for_query(*, context: ContextTypes.DEFAULT_TYPE, query: str) -> set[str]:
    fb = context.application.bot_data.get("feedback_store", {})
    if not isinstance(fb, dict):
        return set()
    lst = fb.get(_norm_text(query), [])
    if not isinstance(lst, list):
        return set()
    return {str(x) for x in lst if isinstance(x, str)}


def _bound_fix_store(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    valid = {
        key: value.strip()
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }
    if len(valid) <= _MAX_FIX_ENTRIES and len(valid) == len(raw):
        return raw
    return dict(list(valid.items())[-_MAX_FIX_ENTRIES:])


def _load_fix_store() -> dict[str, str]:
    """
    query_norm -> good_url
    """
    try:
        if not FIX_STORE.exists():
            return {}
        raw = json.loads(FIX_STORE.read_text(encoding="utf-8"))
        return _bound_fix_store(raw)
    except Exception:
        return {}


def _save_fix_store(data: dict[str, str]) -> None:
    _save_json_atomic(FIX_STORE, _bound_fix_store(data), indent=2)


def _remember_good_fix(*, context: ContextTypes.DEFAULT_TYPE, query: str, good_url: str) -> None:
    qn = _norm_text(query)
    fixes = context.application.bot_data.setdefault("fix_store", {})
    if not isinstance(fixes, dict):
        fixes = {}
        context.application.bot_data["fix_store"] = fixes
    fixes[qn] = good_url
    if len(fixes) > _MAX_FIX_ENTRIES:
        fixes = _bound_fix_store(fixes)
        context.application.bot_data["fix_store"] = fixes
    _save_fix_store(fixes)


def _preferred_fix_url(*, context: ContextTypes.DEFAULT_TYPE, query: str) -> str | None:
    fixes = context.application.bot_data.get("fix_store", {})
    if not isinstance(fixes, dict):
        return None
    return fixes.get(_norm_text(query))
