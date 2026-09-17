"""Создаёт проверенную online-копию канонической SQLite-базы бота."""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_database(source: Path, backup_dir: Path, *, keep_days: int = 14) -> Path:
    """Копирует source через SQLite backup API и проверяет integrity_check."""
    source = Path(source).resolve()
    backup_dir = Path(backup_dir).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")
    if keep_days < 1:
        raise ValueError("keep_days must be positive")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"chat-{stamp}.sqlite3"
    temporary = backup_dir / f".{destination.name}.tmp"

    source_connection = None
    destination_connection = None
    try:
        source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        destination_connection = sqlite3.connect(temporary)
        source_connection.execute("PRAGMA busy_timeout = 10000")
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise sqlite3.DatabaseError(f"integrity_check failed: {result!r}")
        destination_connection.commit()
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()

    try:
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    checksum = _sha256(destination)
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        f"{checksum}  {destination.name}\n", encoding="ascii"
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    for old in backup_dir.glob("chat-*.sqlite3"):
        if old == destination:
            continue
        if datetime.fromtimestamp(old.stat().st_mtime, timezone.utc) < cutoff:
            old.unlink()
            old.with_suffix(old.suffix + ".sha256").unlink(missing_ok=True)
    return destination


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "data" / "chat.sqlite3")
    parser.add_argument("--backup-dir", type=Path, default=root / ".cache" / "db-backups")
    parser.add_argument("--keep-days", type=int, default=14)
    args = parser.parse_args()
    try:
        destination = backup_database(args.source, args.backup_dir, keep_days=args.keep_days)
    except Exception as exc:  # noqa: BLE001
        print(f"database backup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"database backup created: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
