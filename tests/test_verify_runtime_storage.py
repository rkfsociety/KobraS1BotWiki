from __future__ import annotations

import pytest

from app.bot.chat_store import ChatStore
from scripts.verify_runtime_storage import REQUIRED_NAMESPACES, verify_database


def test_verify_runtime_storage_requires_all_namespaces(tmp_path):
    database = tmp_path / "chat.sqlite3"
    store = ChatStore(database)
    try:
        for namespace in REQUIRED_NAMESPACES:
            store.save_state(namespace, {})
    finally:
        store.close()

    result = verify_database(database)

    assert result["integrity"] == "ok"
    assert result["runtime_namespaces"] == len(REQUIRED_NAMESPACES)


def test_verify_runtime_storage_rejects_missing_namespace(tmp_path):
    database = tmp_path / "chat.sqlite3"
    store = ChatStore(database)
    try:
        store.save_state("manual_qa", [])
    finally:
        store.close()

    with pytest.raises(Exception, match="missing runtime namespaces"):
        verify_database(database)
