import sqlite3
import threading
from pathlib import Path

from app.bot.chat_store import ChatMessage, ChatStore


def test_creates_database_schema_and_indexes(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "chat.sqlite3"

    store = ChatStore(database_path)
    try:
        with sqlite3.connect(database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index'"
                )
            }
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        assert {"chat_messages", "rate_limit_events"} <= tables
        assert {"idx_chat_messages_user_id_id", "idx_chat_messages_user_id_created_at"} <= indexes
        assert journal_mode.lower() == "wal"
    finally:
        store.close()


def test_existing_schema_is_migrated_and_message_url_is_preserved(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at REAL NOT NULL,
                reply_to_id INTEGER
            )
            """
        )

    store = ChatStore(database_path)
    try:
        with sqlite3.connect(database_path) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(chat_messages)")
            }
        assert "url" in columns
        message = store.add_message(1, "bot", "Откройте wiki", "wiki", url="https://wiki.example/page")
        assert message.url == "https://wiki.example/page"
        assert store.list_messages(1)[0].url == "https://wiki.example/page"
    finally:
        store.close()


def test_messages_are_isolated_and_listed_in_chronological_order(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        first = store.add_message(1, "user", "first", "telegram")
        second = store.add_message(1, "assistant", "second", "wiki", first.id)
        store.add_message(2, "user", "other", "telegram")

        assert store.list_messages(1) == [
            ChatMessage(first.id, 1, "user", "first", "telegram", first.created_at, None),
            ChatMessage(second.id, 1, "assistant", "second", "wiki", second.created_at, first.id),
        ]
        assert [message.text for message in store.list_messages(2)] == ["other"]
    finally:
        store.close()


def test_messages_support_cursor_pagination(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        messages = [store.add_message(1, "user", str(index), "test") for index in range(5)]

        assert [message.text for message in store.list_messages(1, limit=2)] == ["3", "4"]
        assert [message.text for message in store.list_messages(1, limit=2, before_id=messages[3].id)] == [
            "1",
            "2",
        ]
    finally:
        store.close()


def test_rate_limit_allows_one_request_per_three_seconds(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        assert store.allow_request(1, now=100.0) == (True, 0)
        allowed, retry_after = store.allow_request(1, now=102.0)
        assert not allowed
        assert retry_after == 1
        assert store.allow_request(1, now=103.0) == (True, 0)
    finally:
        store.close()


def test_rate_limit_allows_twenty_requests_per_ten_minutes(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        for index in range(20):
            assert store.allow_request(1, now=100.0 + index * 3.0) == (True, 0)

        allowed, retry_after = store.allow_request(1, now=160.0)
        assert not allowed
        assert retry_after == 540
        assert store.allow_request(1, now=700.0) == (True, 0)
        assert store.allow_request(2, now=160.0) == (True, 0)
    finally:
        store.close()


def test_find_recent_duplicate_returns_matching_user_question_and_bot_reply(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        question = store.add_message(1, "user", "same", "miniapp")
        answer = store.add_message(1, "bot", "answer", "wiki", question.id)
        store.add_message(2, "user", "same", "miniapp")

        assert store.find_recent_duplicate(1, "same", now=question.created_at + 1) == (question, answer)
        assert store.find_recent_duplicate(2, "same", now=question.created_at + 1) is None
        assert store.find_recent_duplicate(1, "same", now=question.created_at + 11) is None
    finally:
        store.close()


def test_prune_user_history_keeps_only_the_newest_500_messages(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    try:
        messages = [store.add_message(1, "user", str(index), "test") for index in range(501)]
        store.add_message(2, "user", "keep", "test")

        store.prune_user_history(1)

        remaining = store.list_messages(1, limit=600)
        assert len(remaining) == 500
        assert remaining[0].id == messages[1].id
        assert remaining[-1].id == messages[-1].id
        assert [message.text for message in store.list_messages(2)] == ["keep"]
    finally:
        store.close()


def test_store_is_safe_for_concurrent_writes(tmp_path: Path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    errors: list[BaseException] = []

    def add_messages() -> None:
        try:
            for index in range(20):
                store.add_message(1, "user", str(index), "test")
        except BaseException as error:  # pragma: no cover - only records thread failures
            errors.append(error)

    threads = [threading.Thread(target=add_messages) for _ in range(4)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not errors
        assert len(store.list_messages(1, limit=100)) == 80
    finally:
        store.close()
