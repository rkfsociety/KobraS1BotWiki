"""Сбор вопросов без ответа (score < MIN_SCORE или нет результатов).

Файл data/missed_questions.json — для анализа и пополнения manual_qa.json.
Формат: список объектов {text, score, best_url, chat_id, count, ts}.
Дубликаты по тексту не дублируются — только обновляется счётчик и время.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from app.bot.git_autopull import project_repo_root

_MAX_ENTRIES = 500
_LOCK = threading.Lock()


def _path() -> Path:
    return project_repo_root() / "data" / "missed_questions.json"


def load_missed_questions() -> list[dict[str, Any]]:
    p = _path()
    try:
        if not p.exists():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _save(entries: list[dict[str, Any]]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def add_missed_question(
    *,
    text: str,
    score: int | float | None,
    best_url: str | None,
    chat_id: int | None = None,
) -> None:
    """Добавить вопрос без ответа. Дубликаты по тексту увеличивают счётчик."""
    text = text.strip()
    if not text:
        return

    with _LOCK:
        entries = load_missed_questions()
        key = text.lower()
        for entry in entries:
            if entry.get("text", "").lower() == key:
                entry["count"] = entry.get("count", 1) + 1
                entry["ts"] = time.time()
                if score is not None:
                    entry["score"] = score
                _save(entries)
                return

        entries.insert(0, {
            "text": text,
            "score": score,
            "best_url": best_url,
            "chat_id": chat_id,
            "count": 1,
            "ts": time.time(),
        })
        if len(entries) > _MAX_ENTRIES:
            del entries[_MAX_ENTRIES:]
        _save(entries)


def delete_missed_question(*, idx: int) -> tuple[bool, str]:
    """Удалить запись по индексу (0-based)."""
    with _LOCK:
        entries = load_missed_questions()
        if idx < 0 or idx >= len(entries):
            return False, "нет такого номера"
        entries.pop(idx)
        _save(entries)
    return True, "удалено"


def clear_missed_questions() -> int:
    """Очистить весь список. Возвращает количество удалённых записей."""
    with _LOCK:
        entries = load_missed_questions()
        count = len(entries)
        _save([])
    return count
