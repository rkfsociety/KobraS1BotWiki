from __future__ import annotations

import sqlite3

from app.bot.chat_store import ChatStore
from scripts.backup_chat_database import backup_database


def test_backup_uses_sqlite_online_backup_and_integrity_check(tmp_path):
    source = tmp_path / "data" / "chat.sqlite3"
    backup_dir = tmp_path / "backups"
    store = ChatStore(source)
    try:
        store.add_telegram_message(
            chat_id=-100,
            topic_id=7,
            telegram_message_id=42,
            user_id=9,
            text="вопрос",
        )
        store.save_state("manual_qa", [{"title": "ответ"}])
    finally:
        store.close()

    backup = backup_database(source, backup_dir, keep_days=14)

    assert backup.is_file()
    assert backup.with_suffix(".sqlite3.sha256").is_file()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 1
        assert connection.execute("SELECT namespace FROM bot_state").fetchone()[0] == "manual_qa"
