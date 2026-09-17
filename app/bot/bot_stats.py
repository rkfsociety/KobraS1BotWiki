"""Сбор статистики бота: топ вики/вопросов + активность чата по часам.

Канонический источник Telegram-метрик — data/chat.sqlite3 через ChatStore.
Агрегаты в bot_data["bot_stats"] и .cache/bot_stats.json оставлены для
совместимости и как fallback для исторического периода до наполнения SQLite.
Формат на диске:
  {
    "wiki_pages": {"<url>": <count>, ...},
    "questions":  {"<normalized_q>": <count>, ...},
    "hourly_activity": [<count_h0>, ..., <count_h23>],  # входящие в разрешённых чатах
    "hourly_activity_kind": "incoming",
    "total_answers": <int>,
    "total_incoming": <int>,
    "user_messages": {"<user_id>": {"user_id": <int>, "label": "...", "count": <int>}, ...},
    "daily_scopes": {"<date>:<chat_id>:<topic_id|all>": {"...": "..."}},
    "last_updated": <unix_ts>
  }
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from heapq import nlargest, nsmallest
from zoneinfo import ZoneInfo

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
_STATS_VERSION = 3
_DAILY_RETENTION_DAYS = 31
_MAX_DAILY_SCOPES = 2048
_STATS_TIMEZONE = ZoneInfo("Europe/Kaliningrad")


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
        "daily_scopes": {},
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


def _today_key() -> str:
    return date.today().isoformat()


def _normalize_date_key(value: Any) -> str | None:
    if value in (None, ""):
        return _today_key()
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    today = date.today()
    if parsed > today or parsed < today - timedelta(days=_DAILY_RETENTION_DAYS - 1):
        return None
    return parsed.isoformat()


def normalize_daily_date(value: Any = None) -> str | None:
    """Проверяет дату дневной статистики и возвращает ISO-формат."""
    return _normalize_date_key(value)


def _daily_epoch_bounds(day: str) -> tuple[float, float]:
    """Возвращает UTC-границы локального календарного дня статистики."""
    start = datetime.fromisoformat(day).replace(tzinfo=_STATS_TIMEZONE)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc).timestamp(), end.astimezone(timezone.utc).timestamp()


def _daily_scope_key(*, day: str, chat_id: int, topic_id: int | None) -> str:
    scope = "all" if topic_id is None else str(topic_id)
    return f"{day}:{chat_id}:{scope}"


def _empty_daily_scope(*, day: str, chat_id: int, topic_id: int | None) -> dict[str, Any]:
    return {
        "date": day,
        "chat_id": chat_id,
        "topic_id": topic_id,
        "total_incoming": 0,
        "total_answers": 0,
        "hourly_activity": [0] * 24,
        "topic_label": "",
        "topics": {},
        "questions": {},
        "wiki_pages": {},
        "user_messages": {},
    }


def _daily_scope_from_stats(
    stats: dict[str, Any], *, day: str, chat_id: int, topic_id: int | None, create: bool
) -> dict[str, Any] | None:
    scopes = stats.get("daily_scopes")
    if not isinstance(scopes, dict):
        if not create:
            return None
        scopes = {}
        stats["daily_scopes"] = scopes
    key = _daily_scope_key(day=day, chat_id=chat_id, topic_id=topic_id)
    scope = scopes.get(key)
    if not isinstance(scope, dict):
        if not create:
            return None
        scope = _empty_daily_scope(day=day, chat_id=chat_id, topic_id=topic_id)
        scopes[key] = scope
    return scope


def _sanitize_daily_scope(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    day = _normalize_date_key(value.get("date"))
    try:
        chat_id = int(value.get("chat_id"))
    except (TypeError, ValueError, OverflowError):
        return None
    topic_raw = value.get("topic_id")
    try:
        topic_id = None if topic_raw in (None, "") else int(topic_raw)
    except (TypeError, ValueError, OverflowError):
        topic_id = None
    if day is None:
        return None
    scope = _empty_daily_scope(day=day, chat_id=chat_id, topic_id=topic_id)
    scope["total_incoming"] = max(0, _safe_int(value.get("total_incoming")))
    scope["total_answers"] = max(0, _safe_int(value.get("total_answers")))
    # Старые версии записывали сюда заголовки ответов бота и показывали их
    # как темы обсуждения. Входящие сообщения пользователей не должны
    # наследовать эти метки, поэтому устаревшие поля намеренно не загружаем.
    hourly = value.get("hourly_activity")
    if isinstance(hourly, list) and len(hourly) == 24:
        scope["hourly_activity"] = [max(0, _safe_int(item)) for item in hourly]
    for field, limit in (("questions", _MAX_UNIQUE_QUESTIONS), ("wiki_pages", _MAX_WIKI_PAGES)):
        raw = value.get(field)
        if isinstance(raw, dict):
            scope[field] = _bound_counter(
                {str(key): max(0, _safe_int(count)) for key, count in raw.items() if isinstance(key, str)},
                max_entries=limit,
            )
    users = value.get("user_messages")
    if isinstance(users, dict):
        loaded: dict[str, dict[str, Any]] = {}
        for key, item in users.items():
            if not isinstance(item, dict):
                continue
            try:
                user_id = int(item.get("user_id") or key)
            except (TypeError, ValueError, OverflowError):
                continue
            loaded[str(user_id)] = {
                "user_id": user_id,
                "label": str(item.get("label") or user_id),
                "count": max(0, _safe_int(item.get("count"))),
            }
        scope["user_messages"] = loaded
    return scope


def _prune_daily_scopes(stats: dict[str, Any]) -> None:
    scopes = stats.get("daily_scopes")
    if not isinstance(scopes, dict):
        stats["daily_scopes"] = {}
        return
    today = date.today()
    normalized: dict[str, dict[str, Any]] = {}
    for value in scopes.values():
        scope = _sanitize_daily_scope(value)
        if scope is None:
            continue
        try:
            scope_day = date.fromisoformat(scope["date"])
        except (TypeError, ValueError):
            continue
        if scope_day < today - timedelta(days=_DAILY_RETENTION_DAYS - 1) or scope_day > today:
            continue
        normalized[_daily_scope_key(day=scope["date"], chat_id=scope["chat_id"], topic_id=scope["topic_id"])] = scope
    if len(normalized) > _MAX_DAILY_SCOPES:
        normalized = dict(sorted(normalized.items(), key=lambda item: item[1]["date"], reverse=True)[:_MAX_DAILY_SCOPES])
    stats["daily_scopes"] = normalized


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
        raw_daily = raw.get("daily_scopes")
        if isinstance(raw_daily, dict):
            stats["daily_scopes"] = raw_daily
            _prune_daily_scopes(stats)
        ver = _safe_int(raw.get("stats_version") or 1, default=1)
        kind = raw.get("hourly_activity_kind")
        hourly = raw.get("hourly_activity")
        # Старая схема считала ответы бота — сбрасываем гистограмму при миграции.
        if ver >= 2 and kind == "incoming" and isinstance(hourly, list) and len(hourly) == 24:
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
            if isinstance(stats, dict):
                _prune_daily_scopes(stats)
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


def _daily_scopes_for_event(
    stats: dict[str, Any], *, day: str, chat_id: int, topic_id: int | None
) -> list[dict[str, Any]]:
    scopes = [_daily_scope_from_stats(stats, day=day, chat_id=chat_id, topic_id=topic_id, create=True)]
    if topic_id is not None:
        scopes.append(_daily_scope_from_stats(stats, day=day, chat_id=chat_id, topic_id=None, create=True))
    return [scope for scope in scopes if scope is not None]


def _bump_daily_user(
    scope: dict[str, Any], *, user_id: int, username: str | None, first_name: str | None
) -> None:
    users = scope.setdefault("user_messages", {})
    if not isinstance(users, dict):
        users = {}
        scope["user_messages"] = users
    key = str(user_id)
    item = users.get(key)
    if not isinstance(item, dict):
        item = {"user_id": user_id, "label": _user_label(user_id=user_id, username=username, first_name=first_name), "count": 0}
        users[key] = item
    item["label"] = _user_label(
        user_id=user_id,
        username=username or item.get("username"),
        first_name=first_name or item.get("first_name"),
    )
    item["count"] = max(0, _safe_int(item.get("count"))) + 1
    if username:
        item["username"] = username
    if first_name:
        item["first_name"] = first_name
    if len(users) > _MAX_TRACKED_USERS:
        rare = nsmallest(
            len(users) - _MAX_TRACKED_USERS,
            users.items(),
            key=lambda pair: _safe_int(pair[1].get("count")) if isinstance(pair[1], dict) else 0,
        )
        for drop_key, _ in rare:
            users.pop(drop_key, None)


def _bump_daily_hour(scope: dict[str, Any], hour: int) -> None:
    hourly = scope.get("hourly_activity")
    if not isinstance(hourly, list) or len(hourly) != 24:
        hourly = [0] * 24
        scope["hourly_activity"] = hourly
    hourly[hour] = max(0, _safe_int(hourly[hour])) + 1


def _bump_daily_counter(scope: dict[str, Any], field: str, key: str, *, limit: int) -> None:
    values = scope.get(field)
    if not isinstance(values, dict):
        values = {}
        scope[field] = values
    values[key] = max(0, _safe_int(values.get(key))) + 1
    _bound_counter(values, max_entries=limit)


def record_incoming_activity(
    bot_data: dict[str, Any],
    *,
    user_id: int | None = None,
    username: str | None = None,
    first_name: str | None = None,
    chat_id: int | None = None,
    topic_id: int | None = None,
    track_daily: bool = True,
) -> None:
    """Учитывает каждое входящее сообщение, которое Telegram доставил боту."""
    stats = _runtime_stats(bot_data)
    now = time.time()
    hour = time.localtime(now).tm_hour
    _bump_hour(stats, hour)
    stats["total_incoming"] = max(0, _safe_int(stats.get("total_incoming", 0))) + 1
    if user_id is not None:
        _bump_user_message(stats, user_id=user_id, username=username, first_name=first_name)
    if chat_id is not None and track_daily:
        day = _today_key()
        for scope in _daily_scopes_for_event(stats, day=day, chat_id=chat_id, topic_id=topic_id):
            scope["total_incoming"] = max(0, _safe_int(scope.get("total_incoming"))) + 1
            _bump_daily_hour(scope, hour)
            if user_id is not None:
                _bump_daily_user(scope, user_id=user_id, username=username, first_name=first_name)
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
    chat_id: int | None = None,
    topic_id: int | None = None,
    topic: str | None = None,
) -> None:
    """Записывает факт ответа бота в счётчики.

    source="wiki"      — ответ ссылкой на вики-страницу (url обязателен)
    source="manual_qa" — ответ из ручного FAQ (url игнорируется)

    Гистограмму по часам не трогает — она считает входящие (record_incoming_activity).
    Аргумент topic сохранён для совместимости, но ответы бота не становятся
    темами дневной активности.
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
    if chat_id is not None:
        day = _today_key()
        for scope in _daily_scopes_for_event(stats, day=day, chat_id=chat_id, topic_id=topic_id):
            scope["total_answers"] = max(0, _safe_int(scope.get("total_answers"))) + 1
            if q_norm:
                _bump_daily_counter(scope, "questions", q_norm, limit=_MAX_UNIQUE_QUESTIONS)
            if source == "wiki" and url:
                _bump_daily_counter(scope, "wiki_pages", url, limit=_MAX_WIKI_PAGES)
    stats["last_updated"] = now

    _persist(bot_data)


def get_top_wiki_pages(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Топ вики-страниц по количеству ответов ботом."""
    if limit <= 0:
        return []
    stats = _canonical_metrics(bot_data) or _stats_from_bot_data(bot_data)
    return nlargest(limit, _counter_items(stats.get("wiki_pages")), key=lambda x: x[1])


def get_top_questions(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Топ вопросов пользователей по частоте."""
    if limit <= 0:
        return []
    stats = _canonical_metrics(bot_data) or _stats_from_bot_data(bot_data)
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


def _canonical_metrics(bot_data: dict[str, Any]) -> dict[str, Any] | None:
    """Возвращает агрегаты Telegram из ChatStore, если база уже наполнена."""
    if not isinstance(bot_data, dict):
        return None
    chat_store = bot_data.get("chat_store")
    metrics_reader = getattr(chat_store, "global_metrics", None)
    if not callable(metrics_reader):
        return None
    try:
        metrics = metrics_reader()
    except Exception:
        log.exception("Не удалось прочитать общую статистику из канонической базы")
        return None
    if not isinstance(metrics, dict):
        return None
    # Пустая новая база не должна обнулять сохраненную совместимую статистику
    # до того, как в нее попадет первое Telegram-сообщение.
    if _safe_int(metrics.get("total_incoming")) or _safe_int(metrics.get("total_answers")):
        return metrics
    return None


def get_hourly_activity(bot_data: dict[str, Any]) -> list[int]:
    """Счётчики входящих сообщений по часам суток (24 элемента, индекс = час)."""
    stats = _canonical_metrics(bot_data) or _stats_from_bot_data(bot_data)
    hourly = stats.get("hourly_activity")
    if isinstance(hourly, list) and len(hourly) == 24:
        return [max(0, _safe_int(value)) for value in hourly]
    return [0] * 24


def get_top_users(bot_data: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Топ участников по числу входящих сообщений в разрешённых чатах."""
    if limit <= 0:
        return []
    stats = _canonical_metrics(bot_data) or _stats_from_bot_data(bot_data)
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
    stats = _canonical_metrics(bot_data) or _stats_from_bot_data(bot_data)
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


def get_total_answers(bot_data: dict[str, Any]) -> int:
    """Возвращает общее число сохранённых ответов бота."""
    stats = _canonical_metrics(bot_data) or _stats_from_bot_data(bot_data)
    return max(0, _safe_int(stats.get("total_answers", 0)))


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


def get_daily_stats(
    bot_data: dict[str, Any], *, chat_id: int, topic_id: int | None = None, day: str | None = None
) -> dict[str, Any]:
    """Возвращает безопасную дневную сводку группы или отдельной темы."""
    normalized_day = _normalize_date_key(day)
    if normalized_day is None:
        normalized_day = _today_key()
    stats = _stats_from_bot_data(bot_data)
    scope = _daily_scope_from_stats(
        stats, day=normalized_day, chat_id=chat_id, topic_id=topic_id, create=False
    )
    if scope is None:
        result = _empty_daily_scope(day=normalized_day, chat_id=chat_id, topic_id=topic_id)
    else:
        result = _sanitize_daily_scope(scope) or _empty_daily_scope(
            day=normalized_day, chat_id=chat_id, topic_id=topic_id
        )
    chat_store = bot_data.get("chat_store")
    if chat_store is not None:
        try:
            start_ts, end_ts = _daily_epoch_bounds(normalized_day)
            daily_metrics = getattr(chat_store, "daily_metrics", None)
            if callable(daily_metrics):
                stored = daily_metrics(
                    chat_id=chat_id,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    topic_id=topic_id,
                )
            else:
                stored = {
                    "total_incoming": chat_store.count_chat_messages(
                        chat_id, start_ts, end_ts, topic_id=topic_id, role="user"
                    ),
                    "total_answers": chat_store.count_chat_messages(
                        chat_id, start_ts, end_ts, topic_id=topic_id, role="bot"
                    ),
                }
            stored_incoming = _safe_int(stored.get("total_incoming"))
            stored_answers = _safe_int(stored.get("total_answers"))
            # До первой записи в новой базе сохраняем доступ к старой агрегированной
            # статистике. После появления сообщений источником становятся только SQL-данные.
            if stored_incoming or stored_answers:
                result.update(
                    {
                        "total_incoming": stored_incoming,
                        "total_answers": stored_answers,
                        "hourly_activity": stored.get("hourly_activity", [0] * 24),
                        "questions": stored.get("questions", {}),
                        "wiki_pages": stored.get("wiki_pages", {}),
                        "user_messages": stored.get("user_messages", {}),
                    }
                )
        except Exception:
            log.exception("Не удалось прочитать дневную статистику из общей базы")
    # Темы сводки не строятся из ответов бота. Поля topics/topic_label,
    # оставшиеся в старом кэше, очищаются через _sanitize_daily_scope.
    result["topics"] = {}
    return result


def get_daily_top_topics(
    bot_data: dict[str, Any], *, chat_id: int, topic_id: int | None = None, day: str | None = None, limit: int = 3
) -> list[tuple[str, int]]:
    if limit <= 0:
        return []
    normalized_day = _normalize_date_key(day) or _today_key()
    chat_store = bot_data.get("chat_store")
    if chat_store is not None:
        try:
            stored = chat_store.list_daily_topics(
                chat_id=chat_id, day=normalized_day, limit=limit
            )
            if stored:
                return stored
        except Exception:
            log.exception("Не удалось прочитать темы дня из общей базы")
    daily = get_daily_stats(bot_data, chat_id=chat_id, topic_id=topic_id, day=day)
    return nlargest(limit, _counter_items(daily.get("topics")), key=lambda item: item[1])
