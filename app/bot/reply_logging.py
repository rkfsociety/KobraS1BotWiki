"""Логирование исходящих ответов бота."""
from __future__ import annotations

import logging

def _log_bot_reply(kind: str, chat_id: int, user_id: int | None = None, **extra: object) -> None:
    """Явная отметка в логе: бот что-то отправил в чат (удобно искать по `bot_reply`)."""
    parts: list[str] = [f"bot_reply kind={kind}", f"chat={chat_id}"]
    if user_id is not None:
        parts.append(f"user={user_id}")
    for key, val in extra.items():
        if val is None:
            continue
        parts.append(f"{key}={val}")
    logging.info(" ".join(parts))
