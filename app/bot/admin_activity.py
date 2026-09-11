"""Учёт модераторских действий админов в разрешённых чатах.

Хранится в bot_data["admin_activity"] и персистится в .cache/admin_activity.json.
 Telegram Bot API присылает события изменения статуса участников и закрепления сообщений,
 поэтому считаем баны, кики, муты и другие такие действия. Удаление чужих сообщений админом
 API отдельно не присылает — отдельно учитываем только delete_bot_msg через /error или /fix.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from typing import Any

from app.bot.stores import _save_interval_elapsed, _save_json_atomic

log = logging.getLogger(__name__)

_ACTIVITY_KEY = "admin_activity"
_SAVE_LOCK = threading.Lock()
_SAVE_INTERVAL = 60.0
_MAX_RECENT = 80
_MAX_ADMINS = 500

_ACTION_LABELS: dict[str, str] = {
    "ban": "бан",
    "kick": "кик",
    "restrict": "мут",
    "unrestrict": "размут",
    "unban": "разбан",
    "promote": "повышение",
    "demote": "понижение",
    "pin": "закреп",
    "delete_bot_msg": "удал. ответа бота",
}


def _activity_path():
    from app.bot.git_autopull import project_repo_root

    return project_repo_root() / ".cache" / "admin_activity.json"


def _empty_activity() -> dict[str, Any]:
    return {
        "admins": {},
        "totals": {},
        "recent": [],
        "last_updated": 0.0,
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _activity_from_bot_data(bot_data: dict[str, Any]) -> dict[str, Any]:
    """Возвращает activity только если runtime-структура действительно dict."""
    if not isinstance(bot_data, dict):
        return {}
    activity = bot_data.get(_ACTIVITY_KEY)
    return activity if isinstance(activity, dict) else {}


def load_admin_activity(bot_data: dict[str, Any]) -> None:
    """Загружает статистику модерации с диска при старте бота."""
    try:
        p = _activity_path()
        if not p.exists():
            bot_data[_ACTIVITY_KEY] = _empty_activity()
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("некорректный формат")
        activity = _empty_activity()
        admins = raw.get("admins")
        if isinstance(admins, dict):
            loaded_admins: dict[str, dict[str, Any]] = {}
            for key, value in admins.items():
                if not isinstance(key, (str, int)) or not isinstance(value, dict):
                    continue
                entry = dict(value)
                counts = value.get("counts")
                if isinstance(counts, dict):
                    entry["counts"] = {str(action): max(0, _safe_int(count)) for action, count in counts.items()}
                loaded_admins[str(key)] = entry
            activity["admins"] = loaded_admins
        totals = raw.get("totals")
        if isinstance(totals, dict):
            activity["totals"] = {str(k): max(0, _safe_int(v)) for k, v in totals.items() if isinstance(k, str)}
        recent = raw.get("recent")
        if isinstance(recent, list):
            activity["recent"] = [x for x in recent if isinstance(x, dict)][-_MAX_RECENT:]
        activity["last_updated"] = _safe_float(raw.get("last_updated", 0.0))
        bot_data[_ACTIVITY_KEY] = activity
        log.info("admin_activity: загружено админов=%d событий=%d", len(activity["admins"]), len(activity["recent"]))
    except Exception as exc:
        log.warning("admin_activity: ошибка загрузки — %s", exc)
        bot_data[_ACTIVITY_KEY] = _empty_activity()


def _persist(bot_data: dict[str, Any], *, force: bool = False) -> None:
    now = time.time()
    with _SAVE_LOCK:
        if not force and not _save_interval_elapsed(
            bot_data.get("_admin_activity_last_save", 0.0), now=now, interval=_SAVE_INTERVAL
        ):
            return
        try:
            p = _activity_path()
            activity = bot_data.get(_ACTIVITY_KEY) or {}
            _save_json_atomic(p, activity)
            bot_data["_admin_activity_last_save"] = now
        except Exception as exc:
            log.warning("admin_activity: ошибка сохранения — %s", exc)


def flush_admin_activity(bot_data: dict[str, Any]) -> None:
    """Принудительно сохраняет свежую статистику перед остановкой процесса."""
    _persist(bot_data, force=True)


def _admin_label(*, user_id: int, username: str | None, first_name: str | None) -> str:
    if username:
        return f"@{username}"
    if first_name:
        return first_name.strip()
    return str(user_id)


def record_admin_action(
    bot_data: dict[str, Any],
    *,
    action: str,
    admin_id: int,
    admin_username: str | None = None,
    admin_first_name: str | None = None,
    target_id: int | None = None,
    target_label: str | None = None,
    chat_id: int | None = None,
) -> None:
    """Записывает одно модераторское действие."""
    if action not in _ACTION_LABELS:
        return

    activity = bot_data.get(_ACTIVITY_KEY)
    if not isinstance(activity, dict):
        activity = _empty_activity()
        bot_data[_ACTIVITY_KEY] = activity
    now = time.time()
    key = str(admin_id)
    admins = activity.get("admins")
    if not isinstance(admins, dict):
        admins = {}
        activity["admins"] = admins
    entry = admins.get(key)
    if not isinstance(entry, dict):
        entry = {
            "user_id": admin_id,
            "label": _admin_label(user_id=admin_id, username=admin_username, first_name=admin_first_name),
            "counts": {},
        }
        admins[key] = entry
    entry["label"] = _admin_label(
        user_id=admin_id,
        username=admin_username or entry.get("username"),
        first_name=admin_first_name or entry.get("first_name"),
    )
    if admin_username:
        entry["username"] = admin_username
    if admin_first_name:
        entry["first_name"] = admin_first_name

    counts = entry.get("counts")
    if not isinstance(counts, dict):
        counts = {}
        entry["counts"] = counts
    counts[action] = max(0, _safe_int(counts.get(action, 0))) + 1

    totals = activity.get("totals")
    if not isinstance(totals, dict):
        totals = {}
        activity["totals"] = totals
    totals[action] = max(0, _safe_int(totals.get(action, 0))) + 1

    recent = activity.get("recent")
    if not isinstance(recent, list):
        recent = []
        activity["recent"] = recent
    recent[:] = [item for item in recent if isinstance(item, dict)]
    recent.append(
        {
            "ts": now,
            "action": action,
            "admin_id": admin_id,
            "admin_label": entry["label"],
            "target_id": target_id,
            "target_label": target_label,
            "chat_id": chat_id,
        }
    )
    if len(recent) > _MAX_RECENT:
        del recent[: len(recent) - _MAX_RECENT]

    if len(admins) > _MAX_ADMINS:
        ranked = sorted(
            admins.items(),
            key=lambda kv: sum(
                max(0, _safe_int(v))
                for v in (kv[1].get("counts") or {}).values()
            ) if isinstance(kv[1], dict) and isinstance(kv[1].get("counts") or {}, dict) else 0,
        )
        for drop_key, _ in ranked[: len(admins) - _MAX_ADMINS]:
            admins.pop(drop_key, None)

    activity["last_updated"] = now
    _persist(bot_data)


def get_admin_activity_summary(bot_data: dict[str, Any], *, limit: int = 15) -> list[dict[str, Any]]:
    """Список админов, отсортированный по сумме всех действий."""
    if limit <= 0:
        return []
    activity = _activity_from_bot_data(bot_data)
    admins = activity.get("admins")
    if not isinstance(admins, dict):
        return []
    rows: list[dict[str, Any]] = []
    for entry in admins.values():
        if not isinstance(entry, dict):
            continue
        counts = entry.get("counts") or {}
        if not isinstance(counts, dict):
            counts = {}
        normalized_counts = {
            str(action): max(0, _safe_int(value))
            for action, value in counts.items()
        }
        total = sum(normalized_counts.values())
        if total <= 0:
            continue
        rows.append(
            {
                "user_id": entry.get("user_id"),
                "label": entry.get("label") or str(entry.get("user_id") or "?"),
                "counts": normalized_counts,
                "total": total,
            }
        )
    rows.sort(key=lambda r: (r["total"], r.get("label") or ""), reverse=True)
    return rows[:limit]


def get_recent_admin_actions(bot_data: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    activity = _activity_from_bot_data(bot_data)
    recent = activity.get("recent")
    if not isinstance(recent, list):
        return []
    return [item for item in reversed(recent[-limit:]) if isinstance(item, dict)]


def get_admin_activity_totals(bot_data: dict[str, Any]) -> dict[str, int]:
    activity = _activity_from_bot_data(bot_data)
    totals = activity.get("totals")
    if not isinstance(totals, dict):
        return {}
    return {
        str(action): max(0, _safe_int(value))
        for action, value in totals.items()
    }


def action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, action)
