"""Безопасная миграция старых агрегатов и доступных текстов в ChatStore.

Скрипт запускается вручную после остановки бота. Он не удаляет исходные JSON,
делает резервную копию runtime-файлов и выполняется повторно без дубликатов.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bot.chat_store import ChatStore  # noqa: E402


_SOURCE_FILES = (
    "data/chat.sqlite3",
    "data/chat.sqlite3-wal",
    "data/chat.sqlite3-shm",
    ".cache/bot_stats.json",
    "data/missed_questions.json",
    ".cache/recent_replies.json",
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _legacy_key(prefix: str, value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _backup_runtime_files(root: Path) -> Path:
    backup = root / ".cache" / "migration-backups" / time.strftime("%Y%m%d-%H%M%S")
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = backup.with_name(f"{backup.name}-{suffix}")
    backup.mkdir(parents=True)
    for relative in _SOURCE_FILES:
        source = root / relative
        if not source.is_file():
            continue
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return backup


def migrate_legacy_data(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, object]:
    """Переносит legacy-источники, сохраняя baseline и текстовые образцы."""
    root = Path(root).resolve()
    paths = {
        "database": root / "data" / "chat.sqlite3",
        "stats": root / ".cache" / "bot_stats.json",
        "missed": root / "data" / "missed_questions.json",
        "replies": root / ".cache" / "recent_replies.json",
    }
    stats = _read_json(paths["stats"], {})
    missed = _read_json(paths["missed"], [])
    replies = _read_json(paths["replies"], [])
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(missed, list):
        missed = []
    if not isinstance(replies, list):
        replies = []

    summary: dict[str, object] = {
        "legacy_scopes": len(stats.get("daily_scopes", {}))
        if isinstance(stats.get("daily_scopes"), dict)
        else 0,
        "missed_samples": sum(1 for item in missed if isinstance(item, dict) and item.get("text")),
        "reply_samples": sum(
            2
            for item in replies
            if isinstance(item, dict) and item.get("question") and item.get("answer")
        ),
        "backup": None,
    }
    if dry_run:
        return summary

    backup = _backup_runtime_files(root)
    summary["backup"] = str(backup)
    store = ChatStore(paths["database"])
    try:
        if stats:
            store.save_legacy_stats(stats, source="bot_stats.json")
            scopes = stats.get("daily_scopes")
            if isinstance(scopes, dict):
                for scope_key, payload in scopes.items():
                    if not isinstance(payload, dict):
                        continue
                    parts = str(scope_key).split(":", 2)
                    if len(parts) != 3:
                        continue
                    chat_id = _as_int(payload.get("chat_id"), _as_int(parts[1]))
                    if chat_id is None:
                        continue
                    topic_raw = payload.get("topic_id")
                    topic_id = None if topic_raw in (None, "", "all") else _as_int(topic_raw)
                    store.save_legacy_daily_scope(
                        scope_key=str(scope_key),
                        chat_id=chat_id,
                        day=str(payload.get("date") or parts[0]),
                        topic_id=topic_id,
                        payload=payload,
                        source="bot_stats.json",
                    )

        imported_missed = 0
        for item in missed:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            chat_id = _as_int(item.get("chat_id"))
            created_at = _as_float(item.get("ts"))
            if not text or chat_id is None or created_at is None:
                continue
            if store.import_legacy_message(
                legacy_key=_legacy_key("missed", item),
                chat_id=chat_id,
                topic_id=None,
                user_id=0,
                role="user",
                text=text,
                source="legacy_missed_questions",
                created_at=created_at,
            ):
                imported_missed += 1

        imported_replies = 0
        for item in replies:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()
            chat_id = _as_int(item.get("chat_id"))
            created_at = _as_float(item.get("ts"))
            if not question or not answer or chat_id is None or created_at is None:
                continue
            key = _legacy_key("reply", item)
            if store.import_legacy_message(
                legacy_key=f"{key}:question",
                chat_id=chat_id,
                topic_id=None,
                user_id=0,
                role="user",
                text=question,
                source="legacy_recent_reply_question",
                created_at=created_at,
            ):
                imported_replies += 1
            if store.import_legacy_message(
                legacy_key=f"{key}:answer",
                chat_id=chat_id,
                topic_id=None,
                user_id=0,
                role="bot",
                text=answer,
                source=str(item.get("source") or "legacy_recent_reply"),
                created_at=created_at,
                url=str(item.get("url") or "") or None,
            ):
                imported_replies += 1
        summary["imported_missed_samples"] = imported_missed
        summary["imported_reply_samples"] = imported_replies
    finally:
        store.close()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Корень checkout проекта")
    parser.add_argument("--dry-run", action="store_true", help="Только показать объём миграции")
    args = parser.parse_args()
    summary = migrate_legacy_data(args.root, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
