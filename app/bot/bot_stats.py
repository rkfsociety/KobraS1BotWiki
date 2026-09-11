"""Сбор статистики бота: топ вики/вопросов + активность чата по часам.

Хранится в bot_data["bot_stats"] и персистируется в .cache/bot_stats.json.
Формат на диске:
  {
    "wiki_pages": {"<url>": <count>, ...},
    "questions":  {"<normalized_q>": <count>, ...},
    "hourly_activity": [<count_h0>, ..., <count_h23>],  # входящие в разрешённых чатах
    "hourly_activity_kind": "incoming",
    "total_answers": <int>,
    "total_incoming": <int>,
    "user_messages": {"<user_id>": {"user_id": <int>, "label": "...", "count": <int>}, ...},
    "last_updated": <unix_ts>
  }
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any
from heapq import nlargest, nsmallest

from app.bot.stores import _save_interval_elapsed, _save_json_atomic

log = logging.getLogger(__name__)

_STATS_KEY = "bot_stats"
_SAVE_LOCK = threading.Lock()
_SAVE_INTERVAL = 60.0
_MAX_UNIQUE_QUESTIONS = 2000
_MAX_WIKI_PAGES = 3000
_MAX_TRACKED_USERS = 3000
_MAX_STATS_CACHE_BYTES = 16 * 1024 * 1024
# v2: hourly_activity = все входящие в allowed-чатах (раньше считались только ответы бота).
_STATS_VERSION = 2


def _stats_path() -> Path:
    from app.bot.git_autopull import project_repo_root
    return project_repo_root() / ".cache" / "bot_stats.json"


def _empty_stats() -> dict[str, Any]:
    return {
        "wiki_pages": {},
        "questions": {},
        "hourly_activity": [0] * 24,
        "hourly_activity_kind": "incoming",
        "total_answers": 0,
        "total_incoming": 0,
        "user_messages": {},
        "stats_version": _STATS_VERSION,
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


def _bound_counter(values: dict[str, int], *, max_entries: int) -> dict[str, int]:
    if len(values) <= max_entries:
        return values
    remove_count = len(values) - max_entries
    rare = nsmallest(remove_count, values.items(), key=lambda item: item[1])
    for key, _ in rare:
        values.pop(key, None)
    return values


def load_bot_stats(bot_data: dict[str, Any]) -> None:
    """Загружает статистику с диска при старте бота."""
    try:
        p = _stats_path()
        if not p.exists():
            bot_data[_STATS_KEY] = _empty_stats()
            return
        if p.stat().st_size > _MAX_STATS_CACHE_BYTES:
            bot_data[_STATS_KEY] = _empty_stats()
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("некорректный формат")
        stats = _empty_stats()
        wp = raw.get("wiki_pages")
        if isinstance(wp, dict):
            stats["wiki_pages"] = _bound_counter(
                {k: max(0, _safe_int(v)) for k, v in wp.items() if isinstance(k, str)},
                max_entries=_MAX_WIKI_PAGES,
            )
        qs = raw.get("questions")
        if isinstance(qs, dict):
            stats["questions"] = _bound_counter(
                {k: max(0, _safe_int(v)) for k, v in qs.items() if isinstance(k, str)},
                max_entries=_MAX_UNIQUE_QUESTIONS,
            )
        stats["total_answers"] = max(0, _safe_int(raw.get("total_answers", 0)))
        stats["total_incoming"] = max(0, _safe_int(raw.get("total_incoming", 0)))
        stats["last_updated"] = _safe_float(raw.get("last_updated", 0.0))
        users = raw.get("user_messages")
        if isinstance(users, dict):
            loaded: dict[str, dict[str, Any]] = {}
            for k, v in users.items():
                if not isinstance(v, dict):
                    continue
                try:
                    uid = int(v.get("user_id") or k)
                except (TypeError, ValueError):
                    continue
                loaded[str(uid)] = {
                    "user_id": uid,
                    "label": str(v.get("label") or uid),
                    "count": max(0, _safe_int(v.get("count", 0))),
                }
                if v.get("username"):
                    loaded[str(uid)]["username"] = str(v["username"])
                if v.get("first_name"):
                    loaded[str(uid)]["first_name"] = str(v["first_name"])
            stats["user_messages"] = loaded
        ver = _safe_int(raw.get("stats_version") or 1, default=1)
        kind = raw.get("hourly_activity_kind")
        hourly = raw.get("hourly_activity")
        # Старая схема считала ответы бота — сбрасываем гистограмму при миграции.
        if ver >= _STATS_VERSION and kind == "incoming" and isinstance(hourly, list) and len(hourly) == 24:
            stats["hourly_activity"] = [max(0, _safe_int(x)) for x in hourly]
        else:
            stats["hourly_activity"] = [0] * 24
            stats["total_incoming"] = 0
            log.info("bot_stats: hourly_activity сброшена (миграция на входящие сообщения)")
        stats["stats_version"] = _STATS_VERSION
        stats["hourly_activity_kind"] = "incoming"
        bot_data[_STATS_KEY] = stats
        log.info(
            "bot_stats: загружено wiki_pages=%d вопросов=%d итого=%d",
            len(stats["wiki_pages"]),
            len(stats["questions"]),
            stats["total_answers"],
        )
    except Exception as exc:
        log.warning("bot_stats: ошибка загрузки — %s", exc)
        bot_data[_STATS_KEY] = _empty_stats()


def _persist(bot_data: dict[str, Any], *, force: bool = False) -> None:
    now = time.time()
    with _SAVE_LOCK:
        if not force and not _save_interval_elapsed(
            bot_data.get("_bot_stats_last_save", 0.0), now=now, interval=_SAVE_INTERVAL
        ):
            return
        try:
            p = _stats_path()
            stats = bot_data.get(_STATS_KEY) or {}
            _save_json_atomic(p, stats)
            bot_data["_bot_stats_last_save"] = now
        except Exception as exc:
            log.warning("bot_stats: ошибка сохранения — %s", exc)


def _runtime_stats(bot_data: dict[str, Any]) -> dict[str, Any]:
    """Возвращает изменяемую runtime-структуру статистики, восстанавливая мусор."""
    stats = bot_data.get(_STATS_KEY)
    if not isinstance(stats, dict):
        stats = _empty_stats()
        bot_data[_STATS_KEY] = stats
    return stats


def flush_bot_stats(bot_data: dict[str, Any]) -> None:
    """Принудительно сохраняет свежую статистику перед остановкой процесса."""
    _persist(bot_data, force=True)


def _bump_hour(stats: dict[str, Any], hour: int) -> None:
    hourly: list[int] = stats.setdefault("hourly_activity", [0] * 24)
    if isinstance(hourly, list) and len(hourly) == 24:
        hourly[hour] += 1
    else:
        stats["hourly_activity"] = [0] * 24
        stats["hourly_activity"][hour] = 1


def _user_label(*, user_id: int, username: str | None, first_name: str | None) -> str:
    if username:
        return f"@{username}"
    if first_name:
        return first_name.strip()
    return str(user_id)


def _bump_user_message(
    stats: dict[str, Any],
    *,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    users = stats.get("user_messages")
    if not isinstance(users, dict):
        users = {}
        stats["user_messages"] = users
    key = str(user_id)
    entry = users.get(key)
    if not isinstance(entry, dict):
        entry = {
            "user_id": user_id,
            "label": _user_label(user_id=user_id, username=username, first_name=first_name),
            "count": 0,
        }
        users[key] = entry
    entry["label"] = _user_label(
        user_id=user_id,
        username=username or entry.get("username"),
        first_name=first_name or entry.get("first_name"),
    )
    if username:
        entry["username"] = username
    if first_name:
        entry["first_name"] = first_name
    entry["count"] = max(0, _safe_int(entry.get("count", 0))) + 1

    if len(users) > _MAX_TRACKED_USERS:
        remove_count = len(users) - _MAX_TRACKED_USERS
        ranked = nsmallest(
            remove_count,
            users.items(),
            key=lambda kv: _safe_int(kv[1].get("count", 0)) if isinstance(kv[1], dict) else 0,
        )
        for drop_key, _ in ranked:
            users.pop(drop_key, None)


def record_incoming_activity(
    bot_data: dict[str, Any],
    *,
    user_id: int | None = None,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    """Учитывает каждое входящее сообщение, которое Telegram доставил боту."""
    stats = _runtime_stats(bot_data)
    now = time.time()
    hour = time.localtime(now).tm_hour
    _bump_hour(stats, hour)
    stats["total_incoming"] = max(0, _safe_int(stats.get("total_incoming", 0))) + 1
    if user_id is not None:
        _bump_user_message(stats, user_id=user_id, username=username, first_name=first_name)
    stats["hourly_activity_kind"] = "incoming"
    stats["stats_version"] = _STATS_VERSION
    stats["last_updated"] = now
    _persist(bot_data)


def record_answer(
    bot_data: dict[str, Any],
    *,
    url: str,
    question: str,
    source: str,
) -> None:
    """Записывает факт ответа бота в счётчики.

    source="wiki"      — ответ ссылкой на вики-страницу (url обязателен)
    source="manual_qa" — ответ из ручного FAQ (url игнорируется)

    Гистограмму по часам не трогает — она считает входящие (record_incoming_activity).
    """
    stats = _runtime_stats(bot_data)

    now = time.time()

    if source == "wiki" and url:
        pages = stats.get("wiki_pages")
        if not isinstance(pages, dict):
            pages = {}
            stats["wiki_pages"] = pages
        pages[url] = max(0, _safe_int(pages.get(url, 0))) + 1
        _bound_counter(pages, max_entries=_MAX_WIKI_PAGES)

    q_norm = " ".join((question or "").strip().lower().split())
    if q_norm:
        questions = stats.get("questions")
        if not isinstance(questions, dict):
            questions = {}
            stats["questions"] = questions
        questions[q_norm] = max(0, _safe_int(questions.get(q_norm, 0))) + 1
        _bound_counter(questions, max_entries=_MAX_UNIQUE_QUESTIONS)

    stats["total_answers"] = max(0, _safe_int(stats.get("total_answers", 0))) + 1
    stats["last_updated"] = now

    _persist(bot_data)


def get_top_wiki_pages(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Топ вики-страниц по количеству ответов ботом."""
    if limit <= 0:
        return []
    stats = _stats_from_bot_data(bot_data)
    return nlargest(limit, _counter_items(stats.get("wiki_pages")), key=lambda x: x[1])


def get_top_questions(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Топ вопросов пользователей по частоте."""
    if limit <= 0:
        return []
    stats = _stats_from_bot_data(bot_data)
    return nlargest(limit, _counter_items(stats.get("questions")), key=lambda x: x[1])


def _stats_from_bot_data(bot_data: dict[str, Any]) -> dict[str, Any]:
    """Возвращает статистику только если runtime-структура действительно dict."""
    if not isinstance(bot_data, dict):
        return {}
    stats = bot_data.get(_STATS_KEY)
    return stats if isinstance(stats, dict) else {}


def _counter_items(value: Any) -> list[tuple[str, int]]:
    """Нормализует счётчик перед сортировкой и отбрасывает мусорные ключи."""
    if not isinstance(value, dict):
        return []
    return [
        (key, max(0, _safe_int(count)))
        for key, count in value.items()
        if isinstance(key, str)
    ]


def get_hourly_activity(bot_data: dict[str, Any]) -> list[int]:
    """Счётчики входящих сообщений по часам суток (24 элемента, индекс = час)."""
    stats = _stats_from_bot_data(bot_data)
    hourly = stats.get("hourly_activity")
    if isinstance(hourly, list) and len(hourly) == 24:
        return [max(0, _safe_int(value)) for value in hourly]
    return [0] * 24


def get_top_users(bot_data: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Топ участников по числу входящих сообщений в разрешённых чатах."""
    if limit <= 0:
        return []
    stats = _stats_from_bot_data(bot_data)
    users = stats.get("user_messages") or {}
    rows: list[dict[str, Any]] = []
    if not isinstance(users, dict):
        return rows
    for entry in users.values():
        if not isinstance(entry, dict):
            continue
        count = max(0, _safe_int(entry.get("count", 0)))
        if count <= 0:
            continue
        rows.append(
            {
                "user_id": entry.get("user_id"),
                "label": entry.get("label") or str(entry.get("user_id") or "?"),
                "count": count,
            }
        )
    return nlargest(limit, rows, key=lambda r: (r["count"], r.get("label") or ""))


def get_stats_metrics(bot_data: dict[str, Any]) -> dict[str, Any]:
    """Возвращает метрики качества: уникальные вопросы/пользователи, коэффициент ответов."""
    stats = _stats_from_bot_data(bot_data)
    total_answers = max(0, _safe_int(stats.get("total_answers", 0)))
    total_incoming = max(0, _safe_int(stats.get("total_incoming", 0)))
    unique_questions = len(stats.get("questions")) if isinstance(stats.get("questions"), dict) else 0
    unique_users = len(stats.get("user_messages")) if isinstance(stats.get("user_messages"), dict) else 0

    answer_rate = 0
    if total_incoming > 0:
        answer_rate = int((total_answers / total_incoming) * 100)

    return {
        "unique_questions": unique_questions,
        "unique_users": unique_users,
        "answer_rate": answer_rate,
        "avg_answers_per_user": int(total_answers / unique_users) if unique_users > 0 else 0,
    }


def get_peak_hours(bot_data: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Возвращает топ часов по активности."""
    if limit <= 0:
        return []
    hourly = get_hourly_activity(bot_data)
    if not hourly:
        return []

    hours = [
        {"hour": h, "count": hourly[h]}
        for h in range(24)
    ]
    hours.sort(key=lambda x: x["count"], reverse=True)
    return hours[:limit]


def get_daily_distribution(bot_data: dict[str, Any]) -> dict[str, int]:
    """Возвращает распределение активности по дням недели (если данные собираются)."""
    stats = _stats_from_bot_data(bot_data)
    daily = stats.get("daily_activity")
    if not isinstance(daily, dict):
        daily = {}
    days = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    return {
        days[i] if i < len(days) else f"день_{i}": max(0, _safe_int(daily.get(str(i), 0)))
        for i in range(7)
    }
