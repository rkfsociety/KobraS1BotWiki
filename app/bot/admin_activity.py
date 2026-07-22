"""Учёт модераторских действий админов в разрешённых чатах.

Хранится в bot_data["admin_activity"] и персистится в .cache/admin_activity.json.
 Telegram Bot API присылает события изменения статуса участников и закрепления сообщений,
 поэтому считаем баны, кики, муты и другие такие действия. Удаление чужих сообщений админом
 API отдельно не присылает — отдельно учитываем только delete_bot_msg через /error или /fix.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

_ACTIVITY_KEY = "admin_activity"
_SAVE_LOCK = threading.Lock()
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
            activity["admins"] = {
                str(k): v for k, v in admins.items() if isinstance(k, (str, int)) and isinstance(v, dict)
            }
        totals = raw.get("totals")
        if isinstance(totals, dict):
            activity["totals"] = {str(k): int(v) for k, v in totals.items() if isinstance(k, str)}
        recent = raw.get("recent")
        if isinstance(recent, list):
            activity["recent"] = [x for x in recent if isinstance(x, dict)][-_MAX_RECENT:]
        activity["last_updated"] = float(raw.get("last_updated", 0.0))
        bot_data[_ACTIVITY_KEY] = activity
        log.info("admin_activity: загружено админов=%d событий=%d", len(activity["admins"]), len(activity["recent"]))
    except Exception as exc:
        log.warning("admin_activity: ошибка загрузки — %s", exc)
        bot_data[_ACTIVITY_KEY] = _empty_activity()


def _persist(bot_data: dict[str, Any]) -> None:
    with _SAVE_LOCK:
        try:
            p = _activity_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            activity = bot_data.get(_ACTIVITY_KEY) or {}
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(json.dumps(activity, ensure_ascii=False).encode("utf-8"))
            tmp.replace(p)
        except Exception as exc:
            log.warning("admin_activity: ошибка сохранения — %s", exc)


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

    activity: dict[str, Any] = bot_data.setdefault(_ACTIVITY_KEY, _empty_activity())
    now = time.time()
    key = str(admin_id)
    admins: dict[str, dict[str, Any]] = activity.setdefault("admins", {})
    entry = admins.setdefault(
        key,
        {
            "user_id": admin_id,
            "label": _admin_label(user_id=admin_id, username=admin_username, first_name=admin_first_name),
            "counts": {},
        },
    )
    entry["label"] = _admin_label(
        user_id=admin_id,
        username=admin_username or entry.get("username"),
        first_name=admin_first_name or entry.get("first_name"),
    )
    if admin_username:
        entry["username"] = admin_username
    if admin_first_name:
        entry["first_name"] = admin_first_name

    counts: dict[str, int] = entry.setdefault("counts", {})
    counts[action] = int(counts.get(action, 0)) + 1

    totals: dict[str, int] = activity.setdefault("totals", {})
    totals[action] = int(totals.get(action, 0)) + 1

    recent: list[dict[str, Any]] = activity.setdefault("recent", [])
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
            key=lambda kv: sum(int(v) for v in (kv[1].get("counts") or {}).values()),
        )
        for drop_key, _ in ranked[: len(admins) - _MAX_ADMINS]:
            admins.pop(drop_key, None)

    activity["last_updated"] = now
    _persist(bot_data)


def get_admin_activity_summary(bot_data: dict[str, Any], *, limit: int = 15) -> list[dict[str, Any]]:
    """Список админов, отсортированный по сумме всех действий."""
    activity = bot_data.get(_ACTIVITY_KEY) or {}
    admins = activity.get("admins") or {}
    rows: list[dict[str, Any]] = []
    for entry in admins.values():
        if not isinstance(entry, dict):
            continue
        counts = entry.get("counts") or {}
        if not isinstance(counts, dict):
            counts = {}
        total = sum(int(v) for v in counts.values())
        if total <= 0:
            continue
        rows.append(
            {
                "user_id": entry.get("user_id"),
                "label": entry.get("label") or str(entry.get("user_id") or "?"),
                "counts": {k: int(v) for k, v in counts.items()},
                "total": total,
            }
        )
    rows.sort(key=lambda r: (r["total"], r.get("label") or ""), reverse=True)
    return rows[:limit]


def get_recent_admin_actions(bot_data: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    activity = bot_data.get(_ACTIVITY_KEY) or {}
    recent = activity.get("recent") or []
    if not isinstance(recent, list):
        return []
    return list(reversed(recent[-limit:]))


def get_admin_activity_totals(bot_data: dict[str, Any]) -> dict[str, int]:
    activity = bot_data.get(_ACTIVITY_KEY) or {}
    totals = activity.get("totals") or {}
    if not isinstance(totals, dict):
        return {}
    return {k: int(v) for k, v in totals.items()}


def action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, action)
