"""Каноническое SQLite-хранилище сообщений Mini App и Telegram-групп."""
from __future__ import annotations

import math
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


_STATS_TIMEZONE = ZoneInfo("Europe/Kaliningrad")


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: int
    user_id: int
    role: str
    text: str
    source: str
    created_at: float
    reply_to_id: int | None
    url: str | None = None
    chat_id: int | None = None
    topic_id: int | None = None
    telegram_message_id: int | None = None
    username: str | None = None
    first_name: str | None = None
    legacy: bool = False


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
                    username TEXT,
                    first_name TEXT,
                    chat_id INTEGER,
                    topic_id INTEGER,
                    telegram_message_id INTEGER,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    reply_to_id INTEGER,
                    url TEXT
                );
                CREATE TABLE IF NOT EXISTS rate_limit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE (chat_id, day, title)
                );
                CREATE TABLE IF NOT EXISTS legacy_stats (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    source TEXT NOT NULL,
                    imported_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS legacy_daily_stats (
                    scope_key TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    topic_id INTEGER,
                    payload TEXT NOT NULL,
                    source TEXT NOT NULL,
                    imported_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id_id
                    ON chat_messages (user_id, id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id_created_at
                    ON chat_messages (user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_duplicate_lookup
                    ON chat_messages (user_id, role, text, created_at, id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_role_id
                    ON chat_messages (role, id);
                CREATE INDEX IF NOT EXISTS idx_chat_messages_reply_to_role_user
                    ON chat_messages (reply_to_id, role, user_id);
                CREATE INDEX IF NOT EXISTS idx_rate_limit_events_user_id_created_at
                    ON rate_limit_events (user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_rate_limit_events_created_at
                    ON rate_limit_events (created_at);
                CREATE INDEX IF NOT EXISTS idx_daily_topics_chat_day
                    ON daily_topics (chat_id, day, message_count DESC);
                """
            )
            columns = {
                row[1]
                for row in self._connection.execute("PRAGMA table_info(chat_messages)").fetchall()
            }
            if "url" not in columns:
                self._connection.execute("ALTER TABLE chat_messages ADD COLUMN url TEXT")
            for column, definition in (
                ("username", "TEXT"),
                ("first_name", "TEXT"),
                ("chat_id", "INTEGER"),
                ("topic_id", "INTEGER"),
                ("telegram_message_id", "INTEGER"),
                ("legacy", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column not in columns:
                    self._connection.execute(
                        f"ALTER TABLE chat_messages ADD COLUMN {column} {definition}"
                    )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_created_at
                    ON chat_messages (chat_id, created_at, id)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_topic_created_at
                    ON chat_messages (chat_id, topic_id, created_at, id)
                """
            )
            self._connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_telegram_identity
                    ON chat_messages (chat_id, telegram_message_id)
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
        url: str | None = None,
        chat_id: int | None = None,
        topic_id: int | None = None,
        telegram_message_id: int | None = None,
        username: str | None = None,
        first_name: str | None = None,
    ) -> ChatMessage:
        created_at = time.time()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO chat_messages (
                    user_id, username, first_name, chat_id, topic_id, telegram_message_id,
                    role, text, source, created_at, reply_to_id, url
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, username, first_name, chat_id, topic_id, telegram_message_id,
                    role, text, source, created_at, reply_to_id, url,
                ),
            )
            message_id = int(cursor.lastrowid)
        # Все значения, кроме AUTOINCREMENT id, уже есть у вызывающего кода;
        # не выполняем дополнительный SELECT только ради восстановления строки.
        return ChatMessage(
            id=message_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            role=role,
            text=text,
            source=source,
            created_at=created_at,
            reply_to_id=reply_to_id,
            url=url,
            chat_id=chat_id,
            topic_id=topic_id,
            telegram_message_id=telegram_message_id,
        )

    def add_telegram_message(
        self,
        *,
        chat_id: int,
        topic_id: int | None,
        telegram_message_id: int,
        user_id: int,
        text: str,
        username: str | None = None,
        first_name: str | None = None,
        role: str = "user",
        source: str = "telegram",
        reply_to_id: int | None = None,
        url: str | None = None,
    ) -> ChatMessage:
        """Сохраняет Telegram-сообщение в общей базе идемпотентно."""
        with self._lock:
            existing = self._connection.execute(
                """
                SELECT * FROM chat_messages
                WHERE chat_id = ? AND telegram_message_id = ?
                """,
                (chat_id, telegram_message_id),
            ).fetchone()
            if existing is not None:
                return self._message_from_row(existing)
            try:
                return self.add_message(
                    user_id,
                    role,
                    text,
                    source,
                    reply_to_id=reply_to_id,
                    url=url,
                    chat_id=chat_id,
                    topic_id=topic_id,
                    telegram_message_id=telegram_message_id,
                    username=username,
                    first_name=first_name,
                )
            except sqlite3.IntegrityError:
                # Another worker may have inserted the same Telegram update.
                existing = self._connection.execute(
                    """
                    SELECT * FROM chat_messages
                    WHERE chat_id = ? AND telegram_message_id = ?
                    """,
                    (chat_id, telegram_message_id),
                ).fetchone()
                if existing is None:
                    raise
                return self._message_from_row(existing)

    def add_exchange(
        self,
        user_id: int,
        user_text: str,
        bot_text: str,
        bot_source: str,
        bot_url: str | None = None,
    ) -> tuple[ChatMessage, ChatMessage]:
        """Сохраняет вопрос и ответ как одну неделимую пару сообщений."""
        created_at = time.time()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                user_cursor = self._connection.execute(
                    """
                    INSERT INTO chat_messages (user_id, role, text, source, created_at, reply_to_id, url)
                    VALUES (?, 'user', ?, 'miniapp', ?, NULL, NULL)
                    """,
                    (user_id, user_text, created_at),
                )
                user_message = ChatMessage(
                    id=int(user_cursor.lastrowid),
                    user_id=user_id,
                    role="user",
                    text=user_text,
                    source="miniapp",
                    created_at=created_at,
                    reply_to_id=None,
                )
                bot_cursor = self._connection.execute(
                    """
                    INSERT INTO chat_messages (user_id, role, text, source, created_at, reply_to_id, url)
                    VALUES (?, 'bot', ?, ?, ?, ?, ?)
                    """,
                    (user_id, bot_text, bot_source, created_at, user_message.id, bot_url),
                )
                bot_message = ChatMessage(
                    id=int(bot_cursor.lastrowid),
                    user_id=user_id,
                    role="bot",
                    text=bot_text,
                    source=bot_source,
                    created_at=created_at,
                    reply_to_id=user_message.id,
                    url=bot_url,
                )
                self._connection.commit()
            except sqlite3.Error:
                self._connection.rollback()
                raise
        return user_message, bot_message

    def list_messages(
        self, user_id: int, limit: int = 50, before_id: int | None = None
    ) -> list[ChatMessage]:
        if limit <= 0:
            return []
        query = "SELECT * FROM chat_messages WHERE chat_id IS NULL AND user_id = ?"
        parameters: list[int] = [user_id]
        if before_id is not None:
            query += " AND id < ?"
            parameters.append(before_id)
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._message_from_row(row) for row in reversed(rows)]

    def list_chat_messages(
        self,
        chat_id: int,
        start_ts: float,
        end_ts: float,
        *,
        topic_id: int | None = None,
        role: str | None = "user",
        limit: int | None = None,
        include_legacy: bool = True,
    ) -> list[ChatMessage]:
        """Возвращает сообщения группы за интервал, разделяя форумные темы."""
        if end_ts <= start_ts or (limit is not None and limit <= 0):
            return []
        query = """
            SELECT * FROM chat_messages
            WHERE chat_id = ? AND created_at >= ? AND created_at < ?
        """
        parameters: list[object] = [chat_id, start_ts, end_ts]
        if not include_legacy:
            query += " AND legacy = 0"
        if topic_id is not None:
            query += " AND topic_id = ?"
            parameters.append(topic_id)
        if role is not None:
            query += " AND role = ?"
            parameters.append(role)
        query += " ORDER BY created_at ASC, id ASC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._message_from_row(row) for row in rows]

    def count_chat_messages(
        self,
        chat_id: int,
        start_ts: float,
        end_ts: float,
        *,
        topic_id: int | None = None,
        role: str | None = "user",
    ) -> int:
        """Считает сообщения группы за интервал из канонической базы."""
        query = """
            SELECT COUNT(*) FROM chat_messages
            WHERE chat_id = ? AND created_at >= ? AND created_at < ?
        """
        parameters: list[object] = [chat_id, start_ts, end_ts]
        if topic_id is not None:
            query += " AND topic_id = ?"
            parameters.append(topic_id)
        if role is not None:
            query += " AND role = ?"
            parameters.append(role)
        with self._lock:
            return int(self._connection.execute(query, parameters).fetchone()[0])

    def daily_metrics(
        self,
        *,
        chat_id: int,
        start_ts: float,
        end_ts: float,
        topic_id: int | None = None,
    ) -> dict[str, object]:
        """Агрегирует дневные метрики из одной выборки канонической базы."""
        messages = self.list_chat_messages(
            chat_id, start_ts, end_ts, topic_id=topic_id, role=None, include_legacy=False
        )
        live = self._aggregate_metrics(messages)
        legacy = self._legacy_daily_metrics(chat_id=chat_id, day=self._day_from_bounds(start_ts))
        if topic_id is not None:
            legacy = self._legacy_daily_metrics(
                chat_id=chat_id, day=self._day_from_bounds(start_ts), topic_id=topic_id
            )
        return self._merge_metrics(legacy, live)

    def global_metrics(self) -> dict[str, object]:
        """Агрегирует общую статистику Telegram из канонической базы."""
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM chat_messages
                WHERE chat_id IS NOT NULL AND legacy = 0
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
        live = self._aggregate_metrics([self._message_from_row(row) for row in rows])
        legacy = self._legacy_stats()
        return self._merge_metrics(legacy, live)

    @staticmethod
    def _day_from_bounds(start_ts: float) -> str:
        return datetime.fromtimestamp(start_ts, tz=_STATS_TIMEZONE).date().isoformat()

    def save_legacy_stats(self, payload: dict[str, object], *, source: str) -> None:
        """Сохраняет старый агрегат как baseline, не превращая его в фиктивные сообщения."""
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO legacy_stats (id, payload, source, imported_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    source = excluded.source,
                    imported_at = excluded.imported_at
                """,
                (encoded, source, time.time()),
            )

    def save_legacy_daily_scope(
        self,
        *,
        scope_key: str,
        chat_id: int,
        day: str,
        topic_id: int | None,
        payload: dict[str, object],
        source: str,
    ) -> None:
        """Сохраняет старую дневную сводку в общей БД отдельным baseline-слоем."""
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO legacy_daily_stats
                    (scope_key, chat_id, day, topic_id, payload, source, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope_key) DO UPDATE SET
                    chat_id = excluded.chat_id,
                    day = excluded.day,
                    topic_id = excluded.topic_id,
                    payload = excluded.payload,
                    source = excluded.source,
                    imported_at = excluded.imported_at
                """,
                (scope_key, chat_id, day, topic_id, encoded, source, time.time()),
            )

    def import_legacy_message(
        self,
        *,
        legacy_key: str,
        chat_id: int,
        topic_id: int | None,
        user_id: int,
        role: str,
        text: str,
        source: str,
        created_at: float,
        username: str | None = None,
        first_name: str | None = None,
        url: str | None = None,
    ) -> bool:
        """Импортирует один доступный legacy-образец идемпотентно."""
        with self._lock, self._connection:
            columns = {
                row[1]
                for row in self._connection.execute("PRAGMA table_info(chat_messages)").fetchall()
            }
            if "legacy_key" not in columns:
                self._connection.execute("ALTER TABLE chat_messages ADD COLUMN legacy_key TEXT")
                self._connection.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_messages_legacy_key "
                    "ON chat_messages (legacy_key) WHERE legacy_key IS NOT NULL"
                )
            cursor = self._connection.execute(
                """
                INSERT OR IGNORE INTO chat_messages (
                    user_id, username, first_name, chat_id, topic_id, telegram_message_id,
                    role, text, source, created_at, reply_to_id, url, legacy, legacy_key
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, 1, ?)
                """,
                (
                    user_id, username, first_name, chat_id, topic_id, role, text,
                    source, created_at, url, legacy_key,
                ),
            )
            return cursor.rowcount > 0

    def _legacy_stats(self) -> dict[str, object]:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM legacy_stats WHERE id = 1"
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _legacy_daily_metrics(
        self, *, chat_id: int, day: str, topic_id: int | None = None
    ) -> dict[str, object]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload FROM legacy_daily_stats
                WHERE chat_id = ? AND day = ?
                  AND ((topic_id IS NULL AND ? IS NULL) OR topic_id = ?)
                ORDER BY imported_at DESC LIMIT 1
                """,
                (chat_id, day, topic_id, topic_id),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _merge_metrics(
        baseline: dict[str, object], current: dict[str, object]
    ) -> dict[str, object]:
        """Складывает baseline и новые агрегаты без изменения исходных словарей."""
        result = {
            "total_incoming": int(baseline.get("total_incoming", 0) or 0)
            + int(current.get("total_incoming", 0) or 0),
            "total_answers": int(baseline.get("total_answers", 0) or 0)
            + int(current.get("total_answers", 0) or 0),
            "hourly_activity": [
                int(a or 0) + int(b or 0)
                for a, b in zip(
                    baseline.get("hourly_activity", [0] * 24),
                    current.get("hourly_activity", [0] * 24),
                )
            ],
            "questions": {},
            "wiki_pages": {},
            "user_messages": {},
        }
        for field in ("questions", "wiki_pages"):
            merged: dict[str, int] = {}
            for payload in (baseline.get(field), current.get(field)):
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        if isinstance(key, str):
                            merged[key] = merged.get(key, 0) + int(value or 0)
            result[field] = merged
        users: dict[str, dict[str, object]] = {}
        for payload in (baseline.get("user_messages"), current.get("user_messages")):
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if not isinstance(value, dict):
                    continue
                item = users.setdefault(
                    str(key),
                    {
                        "user_id": value.get("user_id") or key,
                        "label": value.get("label") or key,
                        "count": 0,
                    },
                )
                item["count"] = int(item["count"]) + int(value.get("count", 0) or 0)
                if value.get("label") and item.get("label") in (None, key):
                    item["label"] = value["label"]
        result["user_messages"] = users
        return result

    @staticmethod
    def _aggregate_metrics(messages: list[ChatMessage]) -> dict[str, object]:
        """Строит совместимый набор агрегатов по уже выбранным сообщениям."""
        hourly = [0] * 24
        questions: dict[str, int] = {}
        wiki_pages: dict[str, int] = {}
        users: dict[str, dict[str, object]] = {}
        total_incoming = 0
        total_answers = 0
        for message in messages:
            if message.role == "user":
                total_incoming += 1
                hour = datetime.fromtimestamp(message.created_at, tz=_STATS_TIMEZONE).hour
                hourly[hour] += 1
                question = " ".join(message.text.lower().split())
                if question:
                    questions[question] = questions.get(question, 0) + 1
                key = str(message.user_id)
                item = users.setdefault(
                    key,
                    {
                        "user_id": message.user_id,
                        "label": message.username or message.first_name or key,
                        "count": 0,
                    },
                )
                item["count"] = int(item["count"]) + 1
            elif message.role == "bot":
                total_answers += 1
                if message.url:
                    wiki_pages[message.url] = wiki_pages.get(message.url, 0) + 1
        return {
            "total_incoming": total_incoming,
            "total_answers": total_answers,
            "hourly_activity": hourly,
            "questions": questions,
            "wiki_pages": wiki_pages,
            "user_messages": users,
        }

    def replace_daily_topics(
        self,
        *,
        chat_id: int,
        day: str,
        topics: list[tuple[str, int]],
        model: str,
    ) -> None:
        """Заменяет AI-темы конкретной группы и календарного дня атомарно."""
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM daily_topics WHERE chat_id = ? AND day = ?",
                (chat_id, day),
            )
            self._connection.executemany(
                """
                INSERT INTO daily_topics (chat_id, day, title, message_count, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (chat_id, day, title[:200], max(0, int(count)), model[:100], now)
                    for title, count in topics
                    if title and int(count) > 0
                ],
            )

    def list_daily_topics(
        self, *, chat_id: int, day: str, limit: int = 10
    ) -> list[tuple[str, int]]:
        """Возвращает сохранённые темы группы за календарный день."""
        if limit <= 0:
            return []
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT title, message_count FROM daily_topics
                WHERE chat_id = ? AND day = ?
                ORDER BY message_count DESC, id ASC LIMIT ?
                """,
                (chat_id, day, limit),
            ).fetchall()
        return [(str(row["title"]), max(0, int(row["message_count"]))) for row in rows]

    def allow_request(self, user_id: int, now: float | None = None) -> tuple[bool, int]:
        now = time.time() if now is None else now
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "DELETE FROM rate_limit_events WHERE created_at <= ?",
                    (now - 600,),
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
            question_row = self._connection.execute(
                """
                SELECT q.*,
                       a.id AS answer_id, a.user_id AS answer_user_id,
                       a.role AS answer_role, a.text AS answer_text,
                       a.source AS answer_source, a.created_at AS answer_created_at,
                       a.reply_to_id AS answer_reply_to_id, a.url AS answer_url
                FROM chat_messages AS q
                JOIN chat_messages AS a
                  ON a.user_id = q.user_id AND a.chat_id IS NULL
                 AND a.role = 'bot' AND a.reply_to_id = q.id
                WHERE q.chat_id IS NULL AND q.user_id = ? AND q.role = 'user' AND q.text = ?
                  AND q.created_at >= ? AND q.created_at <= ?
                ORDER BY q.id DESC, a.id DESC LIMIT 1
                """,
                (user_id, text, now - 10, now),
            ).fetchone()
            if question_row is None:
                return None
        question = ChatMessage(
            id=question_row["id"],
            user_id=question_row["user_id"],
            role=question_row["role"],
            text=question_row["text"],
            source=question_row["source"],
            created_at=question_row["created_at"],
            reply_to_id=question_row["reply_to_id"],
            url=question_row["url"],
        )
        answer = ChatMessage(
            id=question_row["answer_id"],
            user_id=question_row["answer_user_id"],
            role=question_row["answer_role"],
            text=question_row["answer_text"],
            source=question_row["answer_source"],
            created_at=question_row["answer_created_at"],
            reply_to_id=question_row["answer_reply_to_id"],
            url=question_row["answer_url"],
        )
        return question, answer

    def rate_limit_remaining(self, user_id: int, now: float | None = None) -> dict[str, int]:
        """Возвращает текущий остаток короткого и оконного лимитов."""
        now = time.time() if now is None else now
        with self._lock:
            latest = self._connection.execute(
                """
                SELECT created_at FROM rate_limit_events
                WHERE user_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            count = self._connection.execute(
                """
                SELECT COUNT(*) FROM rate_limit_events
                WHERE user_id = ? AND created_at > ?
                """,
                (user_id, now - 600),
            ).fetchone()[0]
        short_remaining = 0 if latest is None else max(0, math.ceil(3 - (now - latest[0])))
        return {"short_remaining": short_remaining, "window_remaining": max(0, 20 - int(count))}

    def list_recent_answers(self, limit: int = 50) -> list[tuple[ChatMessage, ChatMessage]]:
        """Возвращает последние пары вопросов и ответов Mini App."""
        if limit <= 0:
            return []
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT a.id as a_id, a.user_id as a_user, a.role as a_role, a.text as a_text,
                       a.source as a_source, a.created_at as a_created, a.reply_to_id, a.url,
                       q.id as q_id, q.user_id as q_user, q.role as q_role, q.text as q_text,
                       q.source as q_source, q.created_at as q_created
                FROM chat_messages a
                JOIN chat_messages q ON q.id = a.reply_to_id
                WHERE a.chat_id IS NULL AND q.chat_id IS NULL
                  AND a.role = 'bot' AND q.role = 'user'
                ORDER BY a.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result = []
        for row in reversed(rows):
            question = ChatMessage(
                id=row["q_id"],
                user_id=row["q_user"],
                role=row["q_role"],
                text=row["q_text"],
                source=row["q_source"],
                created_at=row["q_created"],
                reply_to_id=None,
            )
            answer = ChatMessage(
                id=row["a_id"],
                user_id=row["a_user"],
                role=row["a_role"],
                text=row["a_text"],
                source=row["a_source"],
                created_at=row["a_created"],
                reply_to_id=row["reply_to_id"],
                url=row["url"],
            )
            result.append((question, answer))
        return result

    def prune_user_history(self, user_id: int, keep: int = 500) -> None:
        keep = max(0, keep)
        with self._lock, self._connection:
            self._connection.execute(
                """
                DELETE FROM chat_messages
                WHERE chat_id IS NULL AND user_id = ? AND id NOT IN (
                    SELECT id FROM chat_messages
                    WHERE chat_id IS NULL AND user_id = ? ORDER BY id DESC LIMIT ?
                )
                """,
                (user_id, user_id, keep),
            )

    def clear_all_history(self) -> int:
        """Удаляет историю Mini App и связанные события ограничения запросов."""
        with self._lock, self._connection:
            deleted = self._connection.execute(
                "DELETE FROM chat_messages WHERE chat_id IS NULL"
            ).rowcount
            self._connection.execute("DELETE FROM rate_limit_events")
        return int(deleted)

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            id=row["id"],
            user_id=row["user_id"],
            username=row["username"],
            first_name=row["first_name"],
            role=row["role"],
            text=row["text"],
            source=row["source"],
            created_at=row["created_at"],
            reply_to_id=row["reply_to_id"],
            url=row["url"],
            chat_id=row["chat_id"],
            topic_id=row["topic_id"],
            telegram_message_id=row["telegram_message_id"],
            legacy=bool(row["legacy"]),
        )
