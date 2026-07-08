"""Сбор вопросов без ответа (score < MIN_SCORE или нет результатов).

Файл data/missed_questions.json — для анализа и пополнения manual_qa.json.
Формат: список объектов {text, score, best_url, chat_id, count, ts}.
Дубликаты по тексту не дублируются — только обновляется счётчик и время.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app.bot.git_autopull import project_repo_root

_MAX_ENTRIES = 500
_LOCK = threading.Lock()

# --- Санитайзер: чистим приватные/запрещённые данные перед сохранением (файл уходит в публичный git) ---
_URL_RE = re.compile(r"(?:https?://|www\.|t\.me/)\S+", re.IGNORECASE)
_BARE_DOMAIN_RE = re.compile(
    r"\b[\w-]+\.(?:ru|com|net|org|io|me|tv|cc|info|biz|ua|by|kz|рф|su|online|store|app|dev)"
    r"(?:/\S*)?\b",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_HANDLE_RE = re.compile(r"(?<![\w])@[A-Za-z][\w]{3,}")
_LONGNUM_RE = re.compile(r"\b\d{12,}\b")  # карты, длинные id — НЕ коды ошибок (4–7 цифр)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s\-()]{0,2}){10,15}(?!\d)")
_PLACEHOLDER_RE = re.compile(r"\[(?:ссылка|email|телефон|ник|номер)\]")


def sanitize_text(text: str) -> str:
    """Заменяет ссылки, email, телефоны, @ники и длинные номера на плейсхолдеры."""
    text = _URL_RE.sub("[ссылка]", text)
    text = _EMAIL_RE.sub("[email]", text)
    text = _BARE_DOMAIN_RE.sub("[ссылка]", text)
    text = _PHONE_RE.sub("[телефон]", text)
    text = _LONGNUM_RE.sub("[номер]", text)
    text = _HANDLE_RE.sub("[ник]", text)
    return re.sub(r"\s+", " ", text).strip()


def is_meaningful_question(sanitized: str) -> bool:
    """True, если после чистки остаётся осмысленный текст (а не только ссылка/контакты)."""
    leftover = _PLACEHOLDER_RE.sub("", sanitized)
    words = re.findall(r"[A-Za-zА-Яа-яЁё]{2,}", leftover)
    return len(words) >= 2


# Политика / война / запрещённые темы — такие сообщения вообще не записываем.
# Список консервативный: только однозначно непечатные темы, без двусмысленных слов
# вроде «выбор» (выбор материала) или «россия/украина» (доставка).
_BLOCKED_TOPIC_RE = re.compile(
    r"(?:"
    # политика / власть / персоны
    r"путин|зеленск|байден|трамп|навальн|кадыр|лукашенк|"
    r"кремл|госдум|президент|правительств|минобороны|оппозиц|митинг|протест|"
    # война / конфликт
    r"\bвойн|\bсво\b|спецоперац|мобилизац|\bмобик|\bфронт|\bвсу\b|обстрел|"
    r"ракетн|\bбпла\b|оккупац|бандеровц|\bхохл|нацбат|"
    # геополитика
    r"санкци|\bнато\b|"
    # запрещённые / чувствительные темы
    r"лгбт|\bгей\b|трансгендер|экстремист|террорист|\bтеракт|"
    r"\bнацист|\bфашист|суицид|самоубийств|наркотик"
    r")",
    re.IGNORECASE,
)


def contains_blocked_topic(text: str) -> bool:
    """True, если в тексте есть политическая/запрещённая тема (не пишем в публичный git)."""
    return bool(_BLOCKED_TOPIC_RE.search(text or ""))


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
    """Добавить вопрос без ответа. Дубликаты по тексту увеличивают счётчик.

    Текст санитизируется (ссылки/контакты → плейсхолдеры); чисто ссылочные/
    контактные сообщения не записываются — файл уходит в публичный git.
    """
    text = sanitize_text(text.strip())
    if not text or not is_meaningful_question(text) or contains_blocked_topic(text):
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


def delete_missed_question_by_text(*, text: str) -> tuple[bool, str]:
    """Удалить запись по тексту (безопасно при сортировке)."""
    key = text.strip().lower()
    with _LOCK:
        entries = load_missed_questions()
        before = len(entries)
        entries = [e for e in entries if e.get("text", "").lower() != key]
        if len(entries) == before:
            return False, "запись не найдена"
        _save(entries)
    return True, "удалено"


def clear_missed_questions() -> int:
    """Очистить весь список. Возвращает количество удалённых записей."""
    with _LOCK:
        entries = load_missed_questions()
        count = len(entries)
        _save([])
    return count


def sanitize_existing() -> tuple[int, int]:
    """Перечистить уже накопленные записи: санитизировать текст и выбросить
    чисто ссылочные/контактные. Возвращает (изменено_или_удалено, осталось)."""
    with _LOCK:
        entries = load_missed_questions()
        cleaned: list[dict[str, Any]] = []
        changed = 0
        for e in entries:
            orig = str(e.get("text", ""))
            new = sanitize_text(orig.strip())
            if not new or not is_meaningful_question(new) or contains_blocked_topic(new):
                changed += 1
                continue
            if new != orig:
                e["text"] = new
                changed += 1
            cleaned.append(e)
        if changed:
            _save(cleaned)
    return changed, len(cleaned)


def try_git_push_missed_questions() -> tuple[bool, str]:
    """git add + commit + push для data/missed_questions.json. Без изменений — no-op."""
    repo = project_repo_root()
    rel = "data/missed_questions.json"
    path = repo / rel
    if not path.is_file():
        return False, "нет файла data/missed_questions.json"
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
        "commit", "-m", "chore(bot): update missed_questions.json",
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
