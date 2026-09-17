"""Переходный слой для JSON-состояния, хранящегося в общей SQLite-базе."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.bot.chat_store import shared_chat_store


def _project_root() -> Path:
    from app.bot.git_autopull import project_repo_root

    return project_repo_root()


def _resolved(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = _project_root() / path
    return path.resolve()


def uses_canonical_database(path: Path) -> bool:
    """Определяет, является ли path штатным legacy-путём production-состояния."""
    resolved = _resolved(path)
    root = _project_root().resolve()
    return resolved.parent == (root / ".cache").resolve() or resolved.parent == (root / "data").resolve()


def load_state(
    namespace: str,
    legacy_path: Path,
    default: Any,
    *,
    max_bytes: int,
) -> tuple[bool, Any]:
    """Читает состояние из SQLite, один раз импортируя legacy JSON.

    Для тестов и явно подменённых временных путей сохраняется старое файловое
    поведение: это позволяет проверять ограничения JSON без касания production
    базы. Штатные пути приложения всегда используют ``data/chat.sqlite3``.
    """
    if not uses_canonical_database(legacy_path):
        return False, None

    store = shared_chat_store()
    if not store.has_state(namespace):
        payload: Any = default
        path = _resolved(legacy_path)
        try:
            if path.exists() and path.stat().st_size <= max_bytes:
                payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = default
        store.save_state(namespace, payload)
    return True, store.load_state(namespace, default)


def save_state(namespace: str, legacy_path: Path, payload: Any) -> bool:
    """Сохраняет штатное состояние в SQLite; возвращает False для test-файлов."""
    if not uses_canonical_database(legacy_path):
        return False
    shared_chat_store().save_state(namespace, payload)
    return True


def migrate_legacy_states() -> None:
    """Импортирует все известные runtime JSON-stores в общей базе при старте."""
    root = _project_root()
    manual_qa_path = root / "data" / "manual_qa.json"
    if not manual_qa_path.exists():
        manual_qa_path = root / ".cache" / "manual_qa.json"
    states = (
        ("manual_qa", manual_qa_path, []),
        ("missed_questions", root / "data" / "missed_questions.json", []),
        ("bad_answers", root / "data" / "bad_answers.json", []),
        ("recent_replies", root / ".cache" / "recent_replies.json", []),
        ("bot_stats", root / ".cache" / "bot_stats.json", {}),
        ("admin_activity", root / ".cache" / "admin_activity.json", {}),
        ("moderation", root / ".cache" / "moderation.json", {}),
        ("clarify_pending", root / ".cache" / "clarify_pending.json", {}),
        ("answer_context", root / ".cache" / "answer_context.json", {}),
        ("feedback", root / ".cache" / "feedback.json", {}),
        ("fixes", root / ".cache" / "fixes.json", {}),
        ("user_context", root / ".cache" / "user_ctx.json", {}),
        ("panel_sessions", root / ".cache" / "panel_sessions.json", {}),
    )
    for namespace, legacy_path, default in states:
        load_state(namespace, legacy_path, default, max_bytes=16 * 1024 * 1024)
