"""Сбор статистики ответов бота: топ вики-страниц, топ вопросов, активность по часам.

Хранится в bot_data["bot_stats"] и персистируется в .cache/bot_stats.json.
Формат на диске:
  {
    "wiki_pages": {"<url>": <count>, ...},
    "questions":  {"<normalized_q>": <count>, ...},
    "hourly_activity": [<count_h0>, ..., <count_h23>],
    "total_answers": <int>,
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


def _stats_path() -> Path:
    from app.bot.git_autopull import project_repo_root
    return project_repo_root() / ".cache" / "bot_stats.json"


def _empty_stats() -> dict[str, Any]:
    return {
        "wiki_pages": {},
        "questions": {},
        "hourly_activity": [0] * 24,
        "total_answers": 0,
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
        hourly = raw.get("hourly_activity")
        if isinstance(hourly, list) and len(hourly) == 24:
            stats["hourly_activity"] = [max(0, int(x)) for x in hourly]
        stats["total_answers"] = max(0, int(raw.get("total_answers", 0)))
        stats["last_updated"] = float(raw.get("last_updated", 0.0))
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
    """
    stats: dict[str, Any] = bot_data.setdefault(_STATS_KEY, _empty_stats())

    now = time.time()
    hour = time.localtime(now).tm_hour

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

    hourly: list[int] = stats.setdefault("hourly_activity", [0] * 24)
    if isinstance(hourly, list) and len(hourly) == 24:
        hourly[hour] += 1
    else:
        stats["hourly_activity"] = [0] * 24
        stats["hourly_activity"][hour] = 1

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
    """Массив счётчиков активности по часам суток (24 элемента, индекс = час)."""
    stats = bot_data.get(_STATS_KEY) or {}
    hourly = stats.get("hourly_activity")
    if isinstance(hourly, list) and len(hourly) == 24:
        return list(hourly)
    return [0] * 24
