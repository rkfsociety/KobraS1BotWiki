"""Чаты, где не удаляем пару «команда /… + ответ бота» (дополняется EPHEMERAL_EXEMPT_CHAT_IDS в .env)."""

from __future__ import annotations

# Не импортируйте из app.bot — цикл с app.config.
DEFAULT_EPHEMERAL_EXEMPT_CHAT_IDS: frozenset[int] = frozenset(
    {
        -1003826125815,
    }
)
