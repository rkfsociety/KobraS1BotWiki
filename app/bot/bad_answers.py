"""Хранение ошибочных ответов бота, отмеченных через веб-панель.

Файл data/bad_answers.json (в git); при необходимости пушится автоматически.
Формат: список объектов {question, answer, url, source, note, ts}.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from app.bot.git_autopull import project_repo_root

_MAX_ENTRIES = 500


def _bad_answers_path() -> Path:
    return project_repo_root() / "data" / "bad_answers.json"


def load_bad_answers() -> list[dict[str, Any]]:
    p = _bad_answers_path()
    try:
        if not p.exists():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        pass
    return []


def save_bad_answers(entries: list[dict[str, Any]]) -> None:
    p = _bad_answers_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def flag_bad_answer(
    *,
    question: str,
    answer: str,
    url: str,
    source: str,
    note: str = "",
) -> None:
    """Добавляет запись об ошибочном ответе в начало списка."""
    entries = load_bad_answers()
    entries.insert(0, {
        "question": question,
        "answer": answer,
        "url": url,
        "source": source,
        "note": note,
        "ts": time.time(),
    })
    if len(entries) > _MAX_ENTRIES:
        del entries[_MAX_ENTRIES:]
    save_bad_answers(entries)


def delete_bad_answer(*, idx: int) -> tuple[bool, str]:
    """Удаляет запись по индексу (0-based)."""
    entries = load_bad_answers()
    if idx < 0 or idx >= len(entries):
        return False, "нет такого номера"
    entries.pop(idx)
    save_bad_answers(entries)
    return True, "удалено"


def try_git_push_bad_answers() -> tuple[bool, str]:
    """git add + commit + push для data/bad_answers.json."""
    repo = project_repo_root()
    rel = "data/bad_answers.json"
    path = repo / rel
    if not path.is_file():
        return False, "нет файла data/bad_answers.json"
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args, cwd=str(repo), env=env,
            capture_output=True, text=True, timeout=120, check=False,
        )

    if not (repo / ".git").exists():
        return False, "нет .git — только локальный файл"

    run(["git", "add", "--", rel])
    diff = run(["git", "diff", "--staged", "--quiet"])
    if diff.returncode == 0:
        return True, "без изменений"

    cm = run([
        "git", "-c", "user.email=bot@kobra-wiki.local",
        "-c", "user.name=KobraS1BotWiki",
        "commit", "-m", "chore(bot): update bad_answers.json",
    ])
    if cm.returncode != 0:
        err = (cm.stderr or cm.stdout or "").strip()
        if "nothing to commit" in err.lower():
            return True, "нечего коммитить"
        return False, err[:500] if err else "git commit failed"

    ps = run(["git", "push"])
    if ps.returncode != 0:
        return False, (ps.stderr or ps.stdout or "git push").strip()[:500]
    return True, "отправлено в origin"
