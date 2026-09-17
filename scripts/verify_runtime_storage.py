"""Проверяет единую SQLite-базу и обязательные runtime-state namespace."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


REQUIRED_NAMESPACES = frozenset({
    "manual_qa",
    "missed_questions",
    "bad_answers",
    "recent_replies",
    "bot_stats",
    "admin_activity",
    "moderation",
    "clarify_pending",
    "answer_context",
    "feedback",
    "fixes",
    "user_context",
    "panel_sessions",
})


def verify_database(path: Path) -> dict[str, object]:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"integrity_check failed: {integrity!r}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing_tables = {"chat_messages", "bot_state"} - tables
        if missing_tables:
            raise sqlite3.DatabaseError(f"missing tables: {sorted(missing_tables)}")
        namespaces = {
            row[0]
            for row in connection.execute("SELECT namespace FROM bot_state")
        }
        missing_namespaces = REQUIRED_NAMESPACES - namespaces
        if missing_namespaces:
            raise sqlite3.DatabaseError(
                f"missing runtime namespaces: {sorted(missing_namespaces)}"
            )
        return {
            "database": str(path),
            "chat_messages": connection.execute(
                "SELECT COUNT(*) FROM chat_messages"
            ).fetchone()[0],
            "runtime_namespaces": len(namespaces),
            "integrity": "ok",
        }
    finally:
        connection.close()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=root / "data" / "chat.sqlite3")
    args = parser.parse_args()
    try:
        print(json.dumps(verify_database(args.database), ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"runtime storage verification failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
