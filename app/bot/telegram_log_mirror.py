"""Зеркало логов консоли в служебный Telegram-канал (OPS_NOTIFY_CHAT_ID)."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from telegram.ext import Application

from app.bot.ops_notify import notify_ops

if TYPE_CHECKING:
    from app.config import Settings

_MAX_CHUNK = 3800


class TelegramLogMirrorHandler(logging.Handler):
    """Копит строки лога (как в консоли) и отдаёт пачками в drain()."""

    def __init__(self, *, redact: str | None = None) -> None:
        super().__init__()
        self._redact = (redact or "").strip() or None
        self._buf: list[str] = []
        self._lock = threading.Lock()
        self._sending = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._sending:
            return
        # Не зацикливать отправку ошибок доставки в тот же канал.
        if record.name.startswith("app.bot.ops_notify"):
            return
        try:
            msg = self.format(record)
            if self._redact and self._redact in msg:
                msg = msg.replace(self._redact, "***")
            with self._lock:
                self._buf.append(msg)
        except Exception:
            self.handleError(record)

    def drain(self, *, max_chars: int = _MAX_CHUNK) -> str | None:
        with self._lock:
            if not self._buf:
                return None
            lines: list[str] = []
            total = 0
            while self._buf and total < max_chars:
                line = self._buf[0]
                add = len(line) + (1 if lines else 0)
                if lines and total + add > max_chars:
                    break
                self._buf.pop(0)
                lines.append(line)
                total += add
            return "\n".join(lines) if lines else None

    def set_sending(self, value: bool) -> None:
        self._sending = value


def attach_telegram_log_mirror(
    *,
    root: logging.Logger,
    formatter: logging.Formatter,
    settings: Settings,
) -> TelegramLogMirrorHandler | None:
    if not settings.ops_log_mirror_enabled or settings.ops_notify_chat_id is None:
        return None
    h = TelegramLogMirrorHandler(redact=settings.telegram_bot_token)
    h.setLevel(settings.ops_log_mirror_level)
    h.setFormatter(formatter)
    root.addHandler(h)
    return h


async def flush_telegram_log_mirror(context) -> None:
    application: Application = context.application
    handler: TelegramLogMirrorHandler | None = application.bot_data.get("log_mirror_handler")
    if handler is None:
        return
    handler.set_sending(True)
    try:
        while True:
            text = handler.drain()
            if not text:
                break
            await notify_ops(application, text)
    finally:
        handler.set_sending(False)
