"""Сбор и хранение статистики ответов бота для веб-панели.

Собирает:
- Топ страниц вики по количеству ответов
- Топ вопросов пользователей по частоте
- Активность по часам суток (0–23)

Данные сохраняются в .cache/bot_stats.json и обновляются при каждом ответе.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_STATS_KEY = "bot_stats"
_STATS_SAVE_LOCK = threading.Lock()
_MAX_QUESTIONS_HISTORY = 5000  # лимит хранящихся вопросов для топа


def _stats_path() -> Path:
    from app.bot.git_autopull import project_repo_root
    return project_repo_root() / ".cache" / "bot_stats.json"


def load_bot_stats(bot_data: dict[str, Any]) -> None:
    """Загружает статистику с диска при старте бота."""
    try:
        p = _stats_path()
        if not p.exists():
            bot_data[_STATS_KEY] = {
                "wiki_pages": {},
                "questions": [],
                "hourly_activity": [0] * 24,
                "total_answers": 0,
                "last_updated": 0,
            }
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("некорректный формат")
        # Нормализация структуры
        stats = {
            "wiki_pages": raw.get("wiki_pages", {}),
            "questions": list(raw.get("questions", []))[-_MAX_QUESTIONS_HISTORY:],
            "hourly_activity": raw.get("hourly_activity", [0] * 24),
            "total_answers": int(raw.get("total_answers", 0)),
            "last_updated": float(raw.get("last_updated", 0)),
        }
        # Гарантируем корректность hourly_activity
        if not isinstance(stats["hourly_activity"], list) or len(stats["hourly_activity"]) != 24:
            stats["hourly_activity"] = [0] * 24
        bot_data[_STATS_KEY] = stats
        log.info("bot_stats: загружено %d записей wiki_pages, %d вопросов", 
                 len(stats["wiki_pages"]), len(stats["questions"]))
    except Exception as exc:
        log.warning("bot_stats: ошибка загрузки — %s", exc)
        bot_data[_STATS_KEY] = {
            "wiki_pages": {},
            "questions": [],
            "hourly_activity": [0] * 24,
            "total_answers": 0,
            "last_updated": 0,
        }


def save_bot_stats(bot_data: dict[str, Any]) -> None:
    """Атомарно сохраняет статистику на диск."""
    with _STATS_SAVE_LOCK:
        try:
            p = _stats_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            stats = bot_data.get(_STATS_KEY, {})
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
    """Записывает ответ в статистику: счётчик вики-страниц, вопрос, час активности."""
    stats: dict[str, Any] = bot_data.setdefault(_STATS_KEY, {
        "wiki_pages": {},
        "questions": [],
        "hourly_activity": [0] * 24,
        "total_answers": 0,
        "last_updated": 0,
    })
    
    now = time.time()
    hour = time.localtime(now).tm_hour
    
    # Счётчик вики-страниц (только для wiki источника)
    if source == "wiki" and url:
        wiki_pages: dict[str, int] = stats.setdefault("wiki_pages", {})
        wiki_pages[url] = wiki_pages.get(url, 0) + 1
    
    # Сохранение вопроса (нормализованного)
    q_norm = " ".join((question or "").strip().lower().split())
    if q_norm:
        questions: list[dict[str, Any]] = stats.setdefault("questions", [])
        questions.append({"q": q_norm, "ts": now})
        # Обрезаем старые записи
        if len(questions) > _MAX_QUESTIONS_HISTORY:
            del questions[:len(questions) - _MAX_QUESTIONS_HISTORY]
    
    # Активность по часам
    hourly: list[int] = stats.setdefault("hourly_activity", [0] * 24)
    if isinstance(hourly, list) and len(hourly) == 24:
        hourly[hour] = hourly[hour] + 1 if hourly[hour] else 1
    else:
        stats["hourly_activity"] = [0] * 24
        stats["hourly_activity"][hour] = 1
    
    stats["total_answers"] = stats.get("total_answers", 0) + 1
    stats["last_updated"] = now
    
    save_bot_stats(bot_data)


def get_top_wiki_pages(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Возвращает топ URL вики-страниц по количеству ответов."""
    stats = bot_data.get(_STATS_KEY, {})
    wiki_pages = stats.get("wiki_pages", {})
    if not wiki_pages:
        return []
    sorted_pages = sorted(wiki_pages.items(), key=lambda x: x[1], reverse=True)
    return sorted_pages[:limit]


def get_top_questions(bot_data: dict[str, Any], limit: int = 10) -> list[tuple[str, int]]:
    """Возвращает топ вопросов по частоте (агрегация нормализованных вопросов)."""
    stats = bot_data.get(_STATS_KEY, {})
    questions = stats.get("questions", [])
    if not questions:
        return []
    counter = Counter(q["q"] for q in questions)
    return counter.most_common(limit)


def get_hourly_activity(bot_data: dict[str, Any]) -> list[int]:
    """Возвращает массив активности по часам (24 элемента)."""
    stats = bot_data.get(_STATS_KEY, {})
    hourly = stats.get("hourly_activity", [0] * 24)
    if not isinstance(hourly, list) or len(hourly) != 24:
        return [0] * 24
    return hourly


def get_stats_summary(bot_data: dict[str, Any]) -> dict[str, Any]:
    """Полная сводка статистики для дашборда."""
    return {
        "total_answers": bot_data.get(_STATS_KEY, {}).get("total_answers", 0),
        "top_wiki_pages": get_top_wiki_pages(bot_data),
        "top_questions": get_top_questions(bot_data),
        "hourly_activity": get_hourly_activity(bot_data),
        "last_updated": bot_data.get(_STATS_KEY, {}).get("last_updated", 0),
    }
