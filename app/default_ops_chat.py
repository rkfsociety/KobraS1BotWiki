"""Чат для служебных уведомлений (ошибки, перезапуски, старт). Переопределение: OPS_NOTIFY_CHAT_ID в .env."""

from __future__ import annotations

# Не импортируйте из app.bot — цикл с app.config.
# AnycubicWikiBotLog (канал, приватная ссылка t.me/+RwrdGsjeLJgxYzIy)
DEFAULT_OPS_NOTIFY_CHAT_ID: int = -1003826125815
