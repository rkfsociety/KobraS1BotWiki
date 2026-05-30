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

from app.bot.decision_log import telegram_message_link

from app.bot.ops_notify import notify_ops

if TYPE_CHECKING:

    from app.config import Settings

_MAX_CHUNK = 3800

# Полный текст входящего / запроса в зеркале лога (раньше в handlers резали до 120).

LOG_MIRROR_TEXT_MAX = 1500

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

_REASON_RU: dict[str, str] = {

    "not_triggered": "не вопрос и нет @бота / ответа на бота",

    "not_a_question": "не похоже на вопрос",
    "conversational_chatter": "бытовая реплика в чате (не запрос к боту)",

    "marketplace_commerce": "маркетплейс / ТН ВЭД (не тема вики)",

    "non_admin_command": "служебная команда не от админа",

    "cooldown": "кулдаун между ответами",

    "rate_limit": "слишком много ответов в минуту",

    "duplicate": "та же ссылка уже недавно отправлялась",

    "low_score": "низкая уверенность поиска по вики",

    "no_results": "в индексе вики ничего не найдено",

    "not_in_allowed_lists": "чат или тема не в ALLOWED_*",

    "need_printer_model_cooldown": "нужна модель, кулдаун уточнения",

    "error_code_not_found": "код ошибки не найден в вики",

    "error_codes_topic_mismatch": "слово «ошибка» без кода — не раздел error-codes",

    "error_code_ambiguous": "код ошибки — несколько вариантов модели",

    "no_guide_for_model": "гайд не для этой модели",

    "slash_command": "сообщение — команда (обрабатывается отдельно)",

    "model_required": "нужно уточнить модель принтера",

}

_KIND_RU: dict[str, str] = {
    "wiki": "отправлена ссылка на вики",
    "clarify_prompt": "запрошено уточнение модели",
    "manual_qa_message": "ручной ответ (manual_qa)",
    "manual_qa_cmd_wiki": "ручной ответ (/wiki)",
    "generic_help_clarify": "просьба уточнить вопрос",
    "error_code_text": "отправлена карточка кода ошибки",
    "no_matching_guide": "нет гайда для этой модели",
    "printer_design_fact": "справка по конструкции принтера",
    "error_code_clarify_prompt": "уточнение модели для кода ошибки",
    "error_code_wiki": "вики после уточнения кода ошибки",
    "clarify_followup_wiki": "вики после уточнения модели",
    "clarify_correction_wiki": "вики (поправка модели)",
    "clarify_followup_uncertain": "не найдено после уточнения",
    "clarify_correction_uncertain": "не найдено (поправка модели)",
}

_KIND_ICON: dict[str, str] = {
    "wiki": "✅",
    "clarify_prompt": "❓",
    "clarify_followup_wiki": "✅",
    "clarify_correction_wiki": "✅",
    "clarify_followup_uncertain": "🔍",
    "clarify_correction_uncertain": "🔍",
    "manual_qa_message": "📋",
    "manual_qa_cmd_wiki": "📋",
    "generic_help_clarify": "💡",
    "error_code_text": "🔢",
    "error_code_clarify_prompt": "❓",
    "error_code_wiki": "✅",
    "no_matching_guide": "❌",
    "printer_design_fact": "🖨",
}

_LEVEL_ICON = {

    "DEBUG": "🔍",

    "INFO": "ℹ️",

    "WARNING": "⚠️",

    "ERROR": "❌",

    "CRITICAL": "🛑",

}

_RE_SEEN = re.compile(

    r"^seen chat=(?P<chat>-?\d+) user=(?P<user>\S+) has_reply=(?P<reply>\w+)"

    r"(?: reply_mid=(?P<rmid>\S+))? reply_from=(?P<rfrom>\S+)"

    r" mid=(?P<mid>\S+) thread=(?P<thread>\S+) text=(?P<text>.*)$"

)

_RE_BOT_REPLY = re.compile(r"^bot_reply kind=(?P<kind>\S+) chat=(?P<chat>-?\d+)")

_RE_INDEX_PROGRESS = re.compile(

    r"^Индексирование \(постепенно\): (?P<done>\d+)/(?P<total>\d+) \(\+(?P<batch>\d+), всего в памяти: (?P<mem>\d+)\)$"

)

_RE_STARTUP_READY = re.compile(
    r"^startup_ready bot=(\S+) wiki=(\d+) qa=(\d+) codes=(\d+) fix=(\d+) "
    r"pid=(\d+) index_done=(true|false)$"
)
_RE_CLARIFY = re.compile(

    r"^clarify chat=(?P<chat>-?\d+) score=(?P<score>\d+) url=(?P<url>\S+) reason=(?P<reason>\w+)"

    r"(?: mid=(?P<mid>\d+))?(?: thread=(?P<thread>\d+))?$"

)

def _esc(s: str) -> str:
    return html.escape(s or "", quote=False)


def _chat_line(chat_id: str) -> str:
    return f"Чат: <code>{_esc(chat_id)}</code>"


def _split_user_context(user_text: str) -> tuple[str, str]:
    """Разбить user_text на (msg_text, context).

    Формат: «↩ {parent · normalized} · {current · normalized}»
    Текущее сообщение — всё, что идёт после последней части с «↩» в начале.
    Эвристика: берём последний · -сегмент как msg.text (работает для однострочных сообщений).
    """
    if not user_text.startswith("↩ "):
        return user_text, ""
    segs = user_text.split(" · ")
    if len(segs) < 2:
        return "", user_text
    current = segs[-1].strip()
    context = " · ".join(segs[:-1])
    return current, context


def _short_wiki_url(url: str) -> str:
    """wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/nozzle → kobra-s1-combo/nozzle"""
    short = re.sub(r"https?://[^/]+(/en)?", "", url).lstrip("/")
    if len(short) > 70:
        short = "…" + short[-67:]
    return short or url



def _message_link_line(chat_id: str, mid: str | None, thread: str | None = None) -> str | None:

    if not mid or mid in ("None", "?", "none"):

        return None

    try:

        cid = int(chat_id)

        message_id = int(mid)

    except ValueError:

        return None

    tid: int | None = None

    if thread and thread not in ("None", "?", "none"):

        try:

            tid = int(thread)

        except ValueError:

            tid = None

    url = telegram_message_link(cid, message_id, thread_id=tid)

    if not url:

        return None

    return f'🔗 <a href="{_esc(url)}">Перейти к сообщению</a>'

def _user_line(user: str) -> str:

    if user in ("?", "None", "none"):

        return "Пользователь: неизвестен"

    return f"Пользователь: <code>{_esc(user)}</code>"

def _reason_ru(code: str) -> str:

    return _REASON_RU.get(code, code.replace("_", " "))

def _is_skip_log(msg: str) -> bool:
    # Пропуски в зеркало не отправляем — только фактические ответы бота (bot_reply).
    return msg.startswith("skip chat=")

def _format_bot_reply(msg: str) -> str | None:
    m = _RE_BOT_REPLY.match(msg)
    if not m:
        return None

    kind = m.group("kind")
    kind_ru = _KIND_RU.get(kind, kind.replace("_", " "))
    kind_icon = _KIND_ICON.get(kind, "💬")
    chat = m.group("chat")

    user_m = re.search(r"\buser=(\d+)", msg)
    thread_m = re.search(r"\bthread=(\d+)", msg)
    incoming_mid_m = re.search(r"\bmid=(\d+)", msg)
    reply_mid_m = re.search(r"\bmessage_id=(\d+)", msg)
    thread = thread_m.group(1) if thread_m else None

    # user_text: всё между user_text= и reply_text= (или концом строки)
    ut_m = re.search(r"\buser_text=(.+?)(?=\s+reply_text=|$)", msg)
    if not ut_m:
        ut_m = re.search(r"\buser_text=(.+)$", msg)
    user_text_raw = ut_m.group(1).strip() if ut_m else ""
    if not user_text_raw:
        if qm := re.search(r"\bquery=(.+?)(?:\s+\w+=|$)", msg):
            user_text_raw = qm.group(1).strip()

    current_text, context_text = _split_user_context(user_text_raw[:LOG_MIRROR_TEXT_MAX])

    rt_m = re.search(r"\breply_text=(.+)$", msg)
    reply_text = rt_m.group(1) if rt_m else ""

    score_m = re.search(r"\bscore=(\d+)", msg)
    url_m = re.search(r"\burl=(\S+)", msg)
    hints_m = re.search(r"\bhints=(\S+)", msg)
    code_m = re.search(r"\bcode=(\d+)\b", msg)

    lines: list[str] = []

    # ── строка 1: иконка + тип ───────────────────────────────────────
    lines.append(f"{kind_icon} <b>{_esc(kind_ru)}</b>")

    # ── строка 2: чат + пользователь ────────────────────────────────
    meta = f"💬 <code>{_esc(chat)}</code>"
    if user_m:
        meta += f"  👤 <code>{_esc(user_m.group(1))}</code>"
    lines.append(meta)

    # ── строка 3: ссылки на вопрос и ответ ──────────────────────────
    link_parts: list[str] = []
    if incoming_mid_m and (lq := _message_link_line(chat, incoming_mid_m.group(1), thread)):
        link_parts.append(f"📩 {lq}")
    if reply_mid_m and (la := _message_link_line(chat, reply_mid_m.group(1), thread)):
        link_parts.append(f"🤖 {la}")
    if link_parts:
        lines.append("  ".join(link_parts))

    lines.append("")

    # ── текст сообщения пользователя (msg.text) ──────────────────────
    if current_text:
        lines.append(f"📝 {_esc(current_text)}")

    # ── контекст (reply_to) — курсив, укорочен ───────────────────────
    if context_text:
        ctx = context_text if len(context_text) <= 220 else context_text[:220] + "…"
        lines.append(f"<i>{_esc(ctx)}</i>")

    # ── ответ бота (только для не-clarify типов) ─────────────────────
    is_clarify = kind in ("clarify_prompt", "error_code_clarify_prompt")
    if reply_text and not is_clarify:
        first = reply_text.split(" · ")[0][:200]
        lines.append("")
        lines.append(f"🤖 <i>{_esc(first)}</i>")

    # ── итоговая строка: оценка · url · модель · код ─────────────────
    tail: list[str] = []
    if score_m:
        tail.append(f"📊 {score_m.group(1)}")
    if code_m:
        tail.append(f"🔢 <code>{_esc(code_m.group(1))}</code>")
    if url_m:
        tail.append(f"🔗 {_esc(_short_wiki_url(url_m.group(1)))}")
    if hints_m and hints_m.group(1) not in ("-", "None", "none"):
        tail.append(f"🏷 {_esc(hints_m.group(1))}")
    if tail:
        lines.append("")
        lines.append("  ".join(tail))

    return "\n".join(lines)

def format_log_for_telegram(record: logging.LogRecord, *, redact: str | None = None) -> str | None:

    name = record.name

    msg = record.getMessage()

    if redact and redact in msg:

        msg = msg.replace(redact, "***")

    # apscheduler: только «Removed job» (рядом с завершением индекса), остальное — шум

    if name.startswith("apscheduler."):

        if name == "apscheduler.scheduler" and msg.startswith("Removed job"):

            return None

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
        return None

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

    if _is_skip_log(msg):

        return None

    reply = _format_bot_reply(msg)

    if reply:

        return reply

    if _RE_SEEN.match(msg):

        return None

    if msg.startswith("Входящее сообщение chat="):

        return None

    if _RE_CLARIFY.match(msg):

        return None

    if msg.startswith("Команда /update:"):

        return f"🔄 <b>/update</b>\n{_esc(msg)}"

    if msg.startswith("git: ") or msg.startswith("git autopull:"):

        return f"📦 <b>Git</b>\n<code>{_esc(msg)}</code>"

    if msg.startswith("Перезапуск ("):

        return f"🔄 <b>Перезапуск</b>\n{_esc(msg)}"

    m = _RE_STARTUP_READY.match(msg)
    if m:
        bot = m.group(1).lstrip("@")
        # Распаковываем счётчики из лог-строки: wiki/QA/коды/fix-store; fix-store не показываем в зеркале
        wiki, qa, codes, _ = m.group(2), m.group(3), m.group(4), m.group(5)
        idx_ok = m.group(7) == "true"
        tail = " · индекс из кэша" if idx_ok else ""
        return (
            f"🚀 <b>Бот запущен</b> · @{_esc(bot)}\n"
            f"Вики: {wiki} · QA: {qa} · коды: {codes}{tail}"
        )

    if (
        msg.startswith("Бот запущен. Wiki docs:")
        or msg.startswith("Bot username:")
        or msg.startswith("Загружен кэш индекса")
        or msg.startswith("Manual QA:")
        or msg.startswith("Каталог кодов ошибок загружен:")
        or msg.startswith("Fix-store загружен:")
    ):
        return None

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

