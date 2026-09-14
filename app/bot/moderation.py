"""Персистентные предупреждения для команд модерации."""
from __future__ import annotations

import json
import logging
import time
from heapq import nlargest
from typing import Any

from app.bot.constants import MODERATION_STORE
from app.bot.stores import _save_json_atomic

log = logging.getLogger(__name__)

_MAX_ENTRIES = 5000
_MAX_WARNINGS_PER_USER = 20
_MAX_STORE_BYTES = 4 * 1024 * 1024


def _empty_store() -> dict[str, Any]:
    return {"warnings": {}, "last_updated": 0.0}


def _store_path():
    from app.bot.git_autopull import project_repo_root

    return project_repo_root() / MODERATION_STORE


def _timestamp(value: object) -> float:
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if result > 0 else 0.0


def _entry_timestamp(entry: object) -> float:
    if not isinstance(entry, dict):
        return 0.0
    return _timestamp(entry.get("last_updated") or entry.get("ts"))


def _bound_store(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_store()

    raw_warnings = raw.get("warnings")
    if not isinstance(raw_warnings, dict):
        return _empty_store()

    valid: dict[str, list[dict[str, Any]]] = {}
    for key, values in raw_warnings.items():
        if not isinstance(key, str) or not isinstance(values, list):
            continue
        clean: list[dict[str, Any]] = []
        for value in values[-_MAX_WARNINGS_PER_USER:]:
            if not isinstance(value, dict):
                continue
            clean.append(
                {
                    "ts": _timestamp(value.get("ts")),
                    "admin_id": value.get("admin_id"),
                    "admin_label": str(value.get("admin_label") or "администратор"),
                    "reason": str(value.get("reason") or "").strip()[:500],
                }
            )
        if clean:
            valid[key] = clean

    if len(valid) > _MAX_ENTRIES:
        valid = dict(
            nlargest(
                _MAX_ENTRIES,
                valid.items(),
                key=lambda item: _entry_timestamp(item[1][-1] if item[1] else {}),
            )
        )
    return {
        "warnings": valid,
        "last_updated": _timestamp(raw.get("last_updated")),
    }


def load_moderation_store(bot_data: dict[str, Any]) -> None:
    """Загружает предупреждения при старте, отбрасывая повреждённые записи."""
    try:
        path = _store_path()
        if not path.exists() or path.stat().st_size > _MAX_STORE_BYTES:
            bot_data["moderation_store"] = _empty_store()
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        bot_data["moderation_store"] = _bound_store(raw)
    except Exception as exc:
        log.warning("moderation: ошибка загрузки предупреждений — %s", exc)
        bot_data["moderation_store"] = _empty_store()


def _get_store(bot_data: dict[str, Any]) -> dict[str, Any]:
    store = bot_data.get("moderation_store")
    if not isinstance(store, dict):
        store = _empty_store()
        bot_data["moderation_store"] = store
    bounded = _bound_store(store)
    if bounded != store:
        bot_data["moderation_store"] = bounded
        store = bounded
    return store


def _save(bot_data: dict[str, Any]) -> None:
    store = _bound_store(_get_store(bot_data))
    store["last_updated"] = time.time()
    bot_data["moderation_store"] = store
    try:
        _save_json_atomic(_store_path(), store, indent=2)
    except Exception as exc:
        log.warning("moderation: ошибка сохранения предупреждений — %s", exc)


def flush_moderation_store(bot_data: dict[str, Any]) -> None:
    """Сохраняет предупреждения перед остановкой бота."""
    if isinstance(bot_data.get("moderation_store"), dict):
        _save(bot_data)


def _warning_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def add_warning(
    bot_data: dict[str, Any],
    *,
    chat_id: int,
    user_id: int,
    admin_id: int,
    admin_label: str,
    reason: str = "",
) -> int:
    store = _get_store(bot_data)
    warnings = store.setdefault("warnings", {})
    key = _warning_key(chat_id, user_id)
    values = warnings.setdefault(key, [])
    if not isinstance(values, list):
        values = []
        warnings[key] = values
    values.append(
        {
            "ts": time.time(),
            "admin_id": admin_id,
            "admin_label": admin_label[:120],
            "reason": reason.strip()[:500],
        }
    )
    del values[:-_MAX_WARNINGS_PER_USER]
    _save(bot_data)
    return len(values)


def remove_warning(bot_data: dict[str, Any], *, chat_id: int, user_id: int) -> int:
    store = _get_store(bot_data)
    warnings = store.get("warnings")
    if not isinstance(warnings, dict):
        return 0
    key = _warning_key(chat_id, user_id)
    values = warnings.get(key)
    if not isinstance(values, list) or not values:
        return 0
    values.pop()
    if not values:
        warnings.pop(key, None)
    _save(bot_data)
    return len(values)


def clear_warnings(bot_data: dict[str, Any], *, chat_id: int, user_id: int) -> int:
    store = _get_store(bot_data)
    warnings = store.get("warnings")
    if not isinstance(warnings, dict):
        return 0
    key = _warning_key(chat_id, user_id)
    values = warnings.pop(key, [])
    count = len(values) if isinstance(values, list) else 0
    if count:
        _save(bot_data)
    return count


def get_warnings(bot_data: dict[str, Any], *, chat_id: int, user_id: int) -> list[dict[str, Any]]:
    store = _get_store(bot_data)
    warnings = store.get("warnings")
    if not isinstance(warnings, dict):
        return []
    values = warnings.get(_warning_key(chat_id, user_id))
    return [dict(value) for value in values if isinstance(value, dict)] if isinstance(values, list) else []
