"""Базовые user_id разработчиков (дополняются DEVELOPER_USER_IDS в .env через load_settings)."""

from __future__ import annotations

# Не импортируйте из app.bot — иначе цикл с app.config при загрузке пакета.
DEFAULT_DEVELOPER_USER_IDS: frozenset[int] = frozenset(
    {
        5111236617,  # @rkfsociety
    }
)
