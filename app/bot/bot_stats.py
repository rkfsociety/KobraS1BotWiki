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
import threading
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_STATS_KEY = "bot_stats"
_SAVE_LOCK = threading.Lock()
_MAX_UNIQUE_QUESTIONS = 2000
_MAX_TRACKED_USERS = 3000
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


def load_bot_stats(bot_data: dict[str, Any]) -> None:
    """Загружает статистику с диска при старте бота."""
    try:
        p = _stats_path()
        if not p.exists():
            bot_data[_STATS_KEY] = _empty_stats()
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("некорректный формат")
        stats = _empty_stats()
        wp = raw.get("wiki_pages")
        if isinstance(wp, dict):
            stats["wiki_pages"] = {k: int(v) for k, v in wp.items() if isinstance(k, str)}
        qs = raw.get("questions")
        if isinstance(qs, dict):
            stats["questions"] = {k: int(v) for k, v in qs.items() if isinstance(k, str)}
        stats["total_answers"] = max(0, int(raw.get("total_answers", 0)))
        stats["total_incoming"] = max(0, int(raw.get("total_incoming", 0)))
        stats["last_updated"] = float(raw.get("last_updated", 0.0))
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
                    "count": max(0, int(v.get("count", 0))),
                }
                if v.get("username"):
                    loaded[str(uid)]["username"] = str(v["username"])
                if v.get("first_name"):
                    loaded[str(uid)]["first_name"] = str(v["first_name"])
            stats["user_messages"] = loaded
        ver = int(raw.get("stats_version") or 1)
        kind = raw.get("hourly_activity_kind")
        hourly = raw.get("hourly_activity")
        # Старая схема считала ответы бота — сбрасываем гистограмму при миграции.
        if ver >= _STATS_VERSION and kind == "incoming" and isinstance(hourly, list) and len(hourly) == 24:
            stats["hourly_activity"] = [max(0, int(x)) for x in hourly]
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


def _persist(bot_data: dict[str, Any]) -> None:
    with _SAVE_LOCK:
        try:
            p = _stats_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            stats = bot_data.get(_STATS_KEY) or {}
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(json.dumps(stats, ensure_ascii=False).encode("utf-8"))
            tmp.replace(p)
        except Exception as exc:
            log.warning("bot_stats: ошибка сохранения — %s", exc)


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
    users: dict[str, dict[str, Any]] = stats.setdefault("user_messages", {})
    key = str(user_id)
    entry = users.setdefault(
        key,
        {"user_id": user_id, "label": _user_label(user_id=user_id, username=username, first_name=first_name), "count": 0},
    )
    entry["label"] = _user_label(
        user_id=user_id,
        username=username or entry.get("username"),
        first_name=first_name or entry.get("first_name"),
    )
    if username:
        entry["username"] = username
    if first_name:
        entry["first_name"] = first_name
    entry["count"] = int(entry.get("count", 0)) + 1

    if len(users) > _MAX_TRACKED_USERS:
        ranked = sorted(users.items(), key=lambda kv: int((kv[1] or {}).get("count", 0)))
        for drop_key, _ in ranked[: len(users) - _MAX_TRACKED_USERS]:
            users.pop(drop_key, None)


def record_incoming_activity(
    bot_data: dict[str, Any],
    *,
    user_id: int | None = None,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    """Учитывает каждое входящее сообщение, которое Telegram доставил боту."""
    stats: dict[str, Any] = bot_data.setdefault(_STATS_KEY, _empty_stats())
    now = time.time()
    hour = time.localtime(now).tm_hour
    _bump_hour(stats, hour)
    stats["total_incoming"] = int(stats.get("total_incoming", 0)) + 1
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
    stats: dict[str, Any] = bot_data.setdefault(_STATS_KEY, _empty_stats())

    now = time.time()

    if source == "wiki" and url:
        pages: dict[str, int] = stats.setdefault("wiki_pages", {})
        pages[url] = pages.get(url, 0) + 1

    q_norm = " ".join((question or "").strip().lower().split())
    if q_norm:
        questions: dict[str, int] = stats.setdefault("questions", {})
        questions[q_norm] = questions.get(q_norm, 0) + 1
        if len(questions) > _MAX_UNIQUE_QUESTIONS:
            # обрезаем самые редкие вопросы (встречались лишь раз)
            rare = [k for k, v in questions.items() if v == 1]
            for k in rare[: len(questions) - _MAX_UNIQUE_QUESTIONS]:
                del questions[k]

    stats["total_answers"] = stats.get("total_answers", 0) + 1
    stats["last_updated"] = now

    _persist(bot_data)


def get_top_wiki_pages(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Топ вики-страниц по количеству ответов ботом."""
    stats = bot_data.get(_STATS_KEY) or {}
    pages = stats.get("wiki_pages") or {}
    return sorted(pages.items(), key=lambda x: x[1], reverse=True)[:limit]


def get_top_questions(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Топ вопросов пользователей по частоте."""
    stats = bot_data.get(_STATS_KEY) or {}
    questions = stats.get("questions") or {}
    return sorted(questions.items(), key=lambda x: x[1], reverse=True)[:limit]


def get_hourly_activity(bot_data: dict[str, Any]) -> list[int]:
    """Счётчики входящих сообщений по часам суток (24 элемента, индекс = час)."""
    stats = bot_data.get(_STATS_KEY) or {}
    hourly = stats.get("hourly_activity")
    if isinstance(hourly, list) and len(hourly) == 24:
        return list(hourly)
    return [0] * 24


def get_top_users(bot_data: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Топ участников по числу входящих сообщений в разрешённых чатах."""
    stats = bot_data.get(_STATS_KEY) or {}
    users = stats.get("user_messages") or {}
    rows: list[dict[str, Any]] = []
    if not isinstance(users, dict):
        return rows
    for entry in users.values():
        if not isinstance(entry, dict):
            continue
        count = int(entry.get("count", 0))
        if count <= 0:
            continue
        rows.append(
            {
                "user_id": entry.get("user_id"),
                "label": entry.get("label") or str(entry.get("user_id") or "?"),
                "count": count,
            }
        )
    rows.sort(key=lambda r: (r["count"], r.get("label") or ""), reverse=True)
    return rows[:limit]
