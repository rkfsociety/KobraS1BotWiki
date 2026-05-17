"""Зеркало логов в служебный Telegram-канал: по-русски, без техношума apscheduler."""
from __future__ import annotations

import html
import logging
import re
import threading
from datetime import datetime
from typing import TYPE_CHECKING

from telegram.constants import ParseMode
from telegram.ext import Application

from app.bot.ops_notify import notify_ops

if TYPE_CHECKING:
    from app.config import Settings

_MAX_CHUNK = 3800

_SKIP_LOGGER_PREFIXES = (
    "apscheduler.executors.default",
    "httpx",
    "httpcore",
    "urllib3",
    "app.bot.ops_notify",
    "app.bot.telegram_log_mirror",
)

# scheduler: только осмысленные строки; Running/executed — шум
_APSCHEDULER_SKIP_RE = re.compile(
    r'^(Running job |Job ".+?" executed successfully)',
    re.I,
)

_SKIP_REASONS_QUIET = frozenset(
    {
        "not_triggered",
        "not_a_question",
        "non_admin_command",
    }
)

_REASON_RU: dict[str, str] = {
    "not_triggered": "нет @бота и не ответ на бота",
    "not_a_question": "не похоже на вопрос",
    "non_admin_command": "служебная команда не от админа",
    "cooldown": "кулдаун между ответами",
    "rate_limit": "слишком много ответов в минуту",
    "duplicate": "та же ссылка уже недавно отправлялась",
    "low_score": "низкая уверенность поиска по вики",
    "no_results": "в индексе вики ничего не найдено",
    "not_in_allowed_lists": "чат или тема не в ALLOWED_*",
    "need_printer_model_cooldown": "нужна модель, кулдаун уточнения",
    "error_code_not_found": "код ошибки не найден в вики",
    "error_code_ambiguous": "код ошибки — несколько вариантов модели",
    "no_guide_for_model": "гайд не для этой модели",
}

_LEVEL_ICON = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🛑",
}

_RE_SKIP = re.compile(
    r"^skip chat=(?P<chat>-?\d+)(?: user=(?P<user>\d+))? reason=(?P<reason>\w+)"
)
_RE_SKIP_SCORE = re.compile(
    r"^skip chat=(?P<chat>-?\d+) reason=(?P<reason>\w+) score=(?P<score>\d+) min=(?P<min>\d+)"
    r"(?: url=(?P<url>\S+))?$"
)
_RE_SEEN = re.compile(
    r"^seen chat=(?P<chat>-?\d+) user=(?P<user>\S+) has_reply=(?P<reply>\w+)"
    r"(?: reply_mid=(?P<rmid>\S+))? reply_from=(?P<rfrom>\S+) text=(?P<text>.*)$"
)
_RE_BOT_REPLY = re.compile(r"^bot_reply kind=(?P<kind>\S+) chat=(?P<chat>-?\d+)")
_RE_INDEX_PROGRESS = re.compile(
    r"^Индексирование \(постепенно\): (?P<done>\d+)/(?P<total>\d+) \(\+(?P<batch>\d+), всего в памяти: (?P<mem>\d+)\)$"
)
_RE_CLARIFY = re.compile(
    r"^clarify chat=(?P<chat>-?\d+) score=(?P<score>\d+) url=(?P<url>\S+) reason=(?P<reason>\w+)$"
)


def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _chat_line(chat_id: str) -> str:
    return f"Чат: <code>{_esc(chat_id)}</code>"


def _user_line(user: str) -> str:
    if user in ("?", "None", "none"):
        return "Пользователь: неизвестен"
    return f"Пользователь: <code>{_esc(user)}</code>"


def _reason_ru(code: str) -> str:
    return _REASON_RU.get(code, code.replace("_", " "))


def format_log_for_telegram(record: logging.LogRecord, *, redact: str | None = None) -> str | None:
    name = record.name
    msg = record.getMessage()
    if redact and redact in msg:
        msg = msg.replace(redact, "***")

    # apscheduler: только «Removed job» (рядом с завершением индекса), остальное — шум
    if name.startswith("apscheduler."):
        if name == "apscheduler.scheduler" and msg.startswith("Removed job"):
            return "✅ <b>Индексация вики</b>\nФоновая задача снята с расписания"
        return None
    if any(name.startswith(p) for p in _SKIP_LOGGER_PREFIXES):
        return None
    if _APSCHEDULER_SKIP_RE.match(msg):
        return None
    if msg.startswith("update kind="):
        return None

    body = _format_body(msg, record)
    if body is None:
        return None

    ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
    icon = _LEVEL_ICON.get(record.levelname, "•")
    return f"{icon} <b>{ts}</b>\n{body}"


def _format_body(msg: str, record: logging.LogRecord) -> str | None:
    if msg == "Индексация завершена — job index_step отключён":
        return "✅ <b>Индексация вики завершена</b>\nВсе страницы из sitemap загружены в память"

    if msg.startswith("Индексация завершена"):
        return f"✅ <b>Индексация вики</b>\n{_esc(msg)}"

    if msg.startswith("Отправлено уведомление о завершении индексации"):
        m = re.search(r"чат (\S+)", msg)
        if m:
            return f"📣 Уведомление: индексация вики завершена (чат {m.group(1)})"
        return "📣 Уведомление: индексация вики завершена"

    if msg.startswith("Автоподстройка:"):
        return f"⚙️ <b>Индексация</b>\n{_esc(msg)}"

    m = _RE_INDEX_PROGRESS.match(msg)
    if m:
        done, total = int(m.group("done")), int(m.group("total"))
        pct = done * 100 // max(1, total)
        return (
            f"📚 <b>Индексация вики</b>\n"
            f"Прогресс: {done} / {total} ({pct}%)\n"
            f"За шаг: +{m.group('batch')} стр., в памяти: {m.group('mem')}"
        )

    m = _RE_SKIP.match(msg)
    if m:
        reason = m.group("reason")
        if reason in _SKIP_REASONS_QUIET:
            return None
        lines = ["⏭ <b>Пропуск</b>", _chat_line(m.group("chat")), f"Причина: {_esc(_reason_ru(reason))}"]
        if m.group("user"):
            lines.insert(2, _user_line(m.group("user")))
        return "\n".join(lines)

    m = _RE_SKIP_SCORE.match(msg)
    if m:
        reason = m.group("reason")
        if reason in _SKIP_REASONS_QUIET:
            return None
        lines = [
            "⏭ <b>Пропуск</b>",
            _chat_line(m.group("chat")),
            f"Причина: {_esc(_reason_ru(reason))}",
            f"Оценка: {m.group('score')} (порог {m.group('min')})",
        ]
        if m.group("url"):
            lines.append(f"URL: {_esc(m.group('url'))}")
        return "\n".join(lines)

    if msg.startswith("skip chat="):
        chat_m = re.search(r"chat=(-?\d+)", msg)
        reason_m = re.search(r"reason=(\w+)", msg)
        if chat_m and reason_m:
            reason = reason_m.group(1)
            if reason in _SKIP_REASONS_QUIET:
                return None
            return "\n".join(
                [
                    "⏭ <b>Пропуск</b>",
                    _chat_line(chat_m.group(1)),
                    f"Причина: {_esc(_reason_ru(reason))}",
                ]
            )

    m = _RE_SEEN.match(msg)
    if m:
        text = (m.group("text") or "").strip()
        if not text:
            return None
        lines = ["📩 <b>Входящее</b>", _chat_line(m.group("chat")), _user_line(m.group("user"))]
        if m.group("reply") == "true":
            lines.append("Ответ (reply) на другое сообщение")
        lines.append(f"Текст: {_esc(text[:500])}")
        return "\n".join(lines)

    m = _RE_BOT_REPLY.match(msg)
    if m:
        lines = ["✅ <b>Ответ бота</b>", f"Тип: <code>{_esc(m.group('kind'))}</code>", _chat_line(m.group("chat"))]
        sm = re.search(r"score=(\d+)", msg)
        if sm:
            lines.append(f"Оценка вики: {sm.group(1)}")
        um = re.search(r"url=(\S+)", msg)
        if um:
            lines.append(f"Ссылка: {_esc(um.group(1))}")
        return "\n".join(lines)

    if msg.startswith("Входящее сообщение chat="):
        m2 = re.match(r"^Входящее сообщение chat=(-?\d+) user=(\S+): (.*)$", msg)
        if m2:
            return "\n".join(
                [
                    "📩 <b>Входящее</b>",
                    _chat_line(m2.group(1)),
                    _user_line(m2.group(2)),
                    f"Текст: {_esc(m2.group(3)[:500])}",
                ]
            )

    m = _RE_CLARIFY.match(msg)
    if m:
        return "\n".join(
            [
                "❓ <b>Уточнение модели</b>",
                _chat_line(m.group("chat")),
                f"Причина: {_esc(_reason_ru(m.group('reason')))}",
            ]
        )

    if msg.startswith("Команда /update:"):
        return f"🔄 <b>/update</b>\n{_esc(msg)}"

    if msg.startswith("git: ") or msg.startswith("git autopull:"):
        return f"📦 <b>Git</b>\n<code>{_esc(msg)}</code>"

    if msg.startswith("Перезапуск ("):
        return f"🔄 <b>Перезапуск</b>\n{_esc(msg)}"

    if msg.startswith("Бот запущен. Wiki docs:"):
        return f"🚀 <b>Бот запущен</b>\nСтраниц в индексе: {_esc(msg.split(':')[-1].strip())}"

    if msg.startswith("Bot username:"):
        return f"🤖 Имя бота: @{_esc(msg.split(':', 1)[1].strip())}"

    if msg.startswith("Загружен кэш индекса"):
        return f"📂 {_esc(msg)}"

    if msg.startswith("Зеркало лога в Telegram") or msg.startswith("Лог-файл:"):
        return None

    if record.levelno >= logging.WARNING:
        return f"<b>{_esc(record.levelname)}</b>\n{_esc(msg)}"

    if re.search(r"[А-Яа-яЁё]", msg):
        return _esc(msg)

    if record.name == "root" and "chat=" in msg and "=" in msg:
        return None

    return None


class TelegramLogMirrorHandler(logging.Handler):
    def __init__(self, *, redact: str | None = None) -> None:
        super().__init__()
        self._redact = (redact or "").strip() or None
        self._buf: list[str] = []
        self._lock = threading.Lock()
        self._sending = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._sending:
            return
        try:
            line = format_log_for_telegram(record, redact=self._redact)
            if not line:
                return
            with self._lock:
                self._buf.append(line)
        except Exception:
            self.handleError(record)

    def drain(self, *, max_chars: int = _MAX_CHUNK) -> str | None:
        with self._lock:
            if not self._buf:
                return None
            chunks: list[str] = []
            total = 0
            sep = "\n\n──────────\n\n"
            while self._buf and total < max_chars:
                block = self._buf[0]
                add = (len(sep) if chunks else 0) + len(block)
                if chunks and total + add > max_chars:
                    break
                self._buf.pop(0)
                chunks.append(block)
                total += add
            return sep.join(chunks) if chunks else None

    def set_sending(self, value: bool) -> None:
        self._sending = value


def attach_telegram_log_mirror(
    *,
    root: logging.Logger,
    settings: Settings,
) -> TelegramLogMirrorHandler | None:
    if not settings.ops_log_mirror_enabled or settings.ops_notify_chat_id is None:
        return None
    h = TelegramLogMirrorHandler(redact=settings.telegram_bot_token)
    h.setLevel(settings.ops_log_mirror_level)
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
            await notify_ops(application, text, parse_mode=ParseMode.HTML)
    finally:
        handler.set_sending(False)
