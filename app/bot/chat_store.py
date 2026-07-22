from __future__ import annotations

import math
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChatMessage:
    id: int
    user_id: int
    role: str
    text: str
    source: str
    created_at: float
    reply_to_id: int | None


class ChatStore:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    reply_to_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS rate_limit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id_id
                    ON chat_messages (user_id, id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id_created_at
                    ON chat_messages (user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_rate_limit_events_user_id_created_at
                    ON rate_limit_events (user_id, created_at);
                """
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def add_message(
        self,
        user_id: int,
        role: str,
        text: str,
        source: str,
        reply_to_id: int | None = None,
    ) -> ChatMessage:
        created_at = time.time()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO chat_messages (user_id, role, text, source, created_at, reply_to_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, role, text, source, created_at, reply_to_id),
            )
            row = self._connection.execute(
                "SELECT * FROM chat_messages WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return self._message_from_row(row)

    def list_messages(
        self, user_id: int, limit: int = 50, before_id: int | None = None
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []
        query = "SELECT * FROM chat_messages WHERE user_id = ?"
        parameters: list[int] = [user_id]
        if before_id is not None:
            query += " AND id < ?"
            parameters.append(before_id)
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._message_from_row(row) for row in reversed(rows)]

    def allow_request(self, user_id: int, now: float | None = None) -> tuple[bool, int]:
        now = time.time() if now is None else now
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "DELETE FROM rate_limit_events WHERE user_id = ? AND created_at <= ?",
                    (user_id, now - 600),
                )
                latest = self._connection.execute(
                    """
                    SELECT created_at FROM rate_limit_events
                    WHERE user_id = ? ORDER BY created_at DESC LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
                if latest is not None and now - latest[0] < 3:
                    retry_after = math.ceil(3 - (now - latest[0]))
                    self._connection.rollback()
                    return False, max(1, retry_after)

                count = self._connection.execute(
                    """
                    SELECT COUNT(*) FROM rate_limit_events
                    WHERE user_id = ? AND created_at >= ?
                    """,
                    (user_id, now - 600),
                ).fetchone()[0]
                if count >= 20:
                    oldest = self._connection.execute(
                        """
                        SELECT created_at FROM rate_limit_events
                        WHERE user_id = ? AND created_at >= ?
                        ORDER BY created_at ASC LIMIT 1
                        """,
                        (user_id, now - 600),
                    ).fetchone()[0]
                    retry_after = math.ceil(600 - (now - oldest))
                    self._connection.rollback()
                    return False, max(1, retry_after)

                self._connection.execute(
                    "INSERT INTO rate_limit_events (user_id, created_at) VALUES (?, ?)",
                    (user_id, now),
                )
                self._connection.commit()
                return True, 0
            except Exception:
                self._connection.rollback()
                raise

    def find_recent_duplicate(
        self, user_id: int, text: str, now: float | None = None
    ) -> tuple[ChatMessage, ChatMessage] | None:
        now = time.time() if now is None else now
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM chat_messages
                WHERE user_id = ? AND text = ? AND created_at >= ? AND created_at <= ?
                ORDER BY id DESC LIMIT 2
                """,
                (user_id, text, now - 10, now),
            ).fetchall()
        if len(rows) < 2:
            return None
        messages = [self._message_from_row(row) for row in reversed(rows)]
        return messages[0], messages[1]

    def prune_user_history(self, user_id: int, keep: int = 500) -> None:
        keep = max(0, keep)
        with self._lock, self._connection:
            self._connection.execute(
                """
                DELETE FROM chat_messages
                WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM chat_messages
                    WHERE user_id = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (user_id, user_id, keep),
            )

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            id=row["id"],
            user_id=row["user_id"],
            role=row["role"],
            text=row["text"],
            source=row["source"],
            created_at=row["created_at"],
            reply_to_id=row["reply_to_id"],
        )
