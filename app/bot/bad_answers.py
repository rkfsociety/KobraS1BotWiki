"""Хранение ошибочных ответов бота, отмеченных через веб-панель.

Рабочее состояние хранится в общей SQLite-базе; старый JSON используется
только как одноразовый источник миграции и для изолированных тестовых путей.
Формат: список объектов {question, answer, url, source, note, ts}.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from app.bot.git_autopull import project_repo_root
from app.bot.state_store import load_state as load_db_state, save_state as save_db_state
from app.bot.stores import _save_json_atomic

_LOCK = threading.RLock()
_MAX_FILE_BYTES = 16 * 1024 * 1024


def _bad_answers_path() -> Path:
    return project_repo_root() / "data" / "bad_answers.json"


def load_bad_answers() -> list[dict[str, Any]]:
    with _LOCK:
        p = _bad_answers_path()
        is_db, db_raw = load_db_state("bad_answers", p, [], max_bytes=_MAX_FILE_BYTES)
        if is_db:
            return [x for x in db_raw if isinstance(x, dict)] if isinstance(db_raw, list) else []
        try:
            if not p.exists():
                return []
            if p.stat().st_size > _MAX_FILE_BYTES:
                return []
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict)]
        except Exception:
            pass
        return []


def save_bad_answers(entries: list[dict[str, Any]]) -> None:
    with _LOCK:
        p = _bad_answers_path()
        if save_db_state("bad_answers", p, entries):
            return
        _save_json_atomic(p, entries, indent=2)


def flag_bad_answer(
    *,
    question: str,
    answer: str,
    url: str,
    source: str,
    note: str = "",
) -> None:
    """Добавляет запись об ошибочном ответе в начало списка."""
    with _LOCK:
        entries = load_bad_answers()
        entries.insert(0, {
            "question": question,
            "answer": answer,
            "url": url,
            "source": source,
            "note": note,
            "ts": time.time(),
        })
        save_bad_answers(entries)


def delete_bad_answer(*, idx: int) -> tuple[bool, str]:
    """Удаляет запись по индексу (0-based)."""
    with _LOCK:
        entries = load_bad_answers()
        if idx < 0 or idx >= len(entries):
            return False, "нет такого номера"
        entries.pop(idx)
        save_bad_answers(entries)
    return True, "удалено"
