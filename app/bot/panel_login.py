"""Вход в веб-панель через бота (без домена).

Поток:
1. Панель создаёт одноразовый код (`create_login_code`) и показывает ссылку
   ``t.me/<бот>?start=<код>``.
2. Пользователь жмёт Start — сюда приходит ``/start <код>`` (``cmd_start``). Бот
   проверяет, что пользователь — администратор группы ``PANEL_ADMIN_CHAT_ID``,
   и помечает код подтверждённым.
3. Панель опрашивает статус и при подтверждении создаёт сессию.

Стор кодов живёт в ``application.bot_data`` и защищён общим ``threading.Lock`` —
к нему обращаются и поток веб-панели, и асинхронный обработчик бота.
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes

_TTL_SECONDS = 300
_MAX_CODES = 200

log = logging.getLogger(__name__)


def _store(application: Any) -> tuple[dict[str, dict[str, Any]], threading.Lock]:
    lock = application.bot_data.get("panel_login_lock")
    if lock is None:
        # Должен быть создан в lifecycle до старта; на всякий случай — создаём здесь.
        lock = threading.Lock()
        application.bot_data["panel_login_lock"] = lock
    codes = application.bot_data.setdefault("panel_login_codes", {})
    return codes, lock


def _gc(codes: dict[str, dict[str, Any]], now: float) -> None:
    dead = [c for c, r in codes.items() if r.get("exp", 0) < now]
    for c in dead:
        codes.pop(c, None)
    # подстраховка от разрастания
    if len(codes) > _MAX_CODES:
        for c in sorted(codes, key=lambda k: codes[k].get("created", 0))[: len(codes) - _MAX_CODES]:
            codes.pop(c, None)


def create_login_code(application: Any, nonce: str) -> str:
    """Создаёт одноразовый код входа, привязанный к nonce браузера."""
    codes, lock = _store(application)
    code = secrets.token_urlsafe(24)
    now = time.time()
    with lock:
        _gc(codes, now)
        codes[code] = {
            "status": "pending",
            "created": now,
            "exp": now + _TTL_SECONDS,
            "nonce": nonce,
            "uid": None,
            "user": "",
            "consumed": False,
        }
    return code


def get_code_status(application: Any, code: str) -> str:
    """Возвращает 'pending' | 'authorized' | 'denied' | 'expired'."""
    codes, lock = _store(application)
    now = time.time()
    with lock:
        rec = codes.get(code)
        if not rec or rec.get("exp", 0) < now:
            return "expired"
        return str(rec.get("status", "expired"))


def consume_authorized(application: Any, code: str, nonce: str) -> tuple[dict[str, Any] | None, str | None]:
    """Если код подтверждён и nonce совпал — отмечает использованным и возвращает данные пользователя."""
    codes, lock = _store(application)
    now = time.time()
    with lock:
        rec = codes.get(code)
        if not rec or rec.get("exp", 0) < now:
            return None, "expired"
        if not secrets.compare_digest(str(rec.get("nonce", "")), nonce or ""):
            return None, "nonce"
        if rec.get("status") != "authorized":
            return None, str(rec.get("status"))
        if rec.get("consumed"):
            return None, "consumed"
        rec["consumed"] = True
        return {"uid": rec.get("uid"), "user": rec.get("user", "")}, None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start [код] — обычное приветствие или подтверждение входа в панель."""
    msg = update.effective_message
    user = update.effective_user
    if msg is None or user is None:
        return
    args = context.args or []
    settings = context.application.bot_data.get("settings")
    if not args:
        webapp_url = str(getattr(settings, "panel_webapp_url", "") or "").strip()
        keyboard = None
        if webapp_url.startswith("https://"):
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Открыть приложение", web_app=WebAppInfo(webapp_url))]]
            )
        await msg.reply_text(
            "Привет! Я бот-помощник по вики. Задавайте вопросы в группе — постараюсь подсказать.",
            reply_markup=keyboard,
        )
        return

    payload = (args[0] or "").strip()
    codes, lock = _store(context.application)
    now = time.time()
    with lock:
        rec = codes.get(payload)
        valid = bool(rec and rec.get("exp", 0) > now and rec.get("status") == "pending")
    if not valid:
        await msg.reply_text("Ссылка для входа в панель недействительна или истекла. Откройте панель и начните вход заново.")
        return

    chat_id = getattr(settings, "panel_admin_chat_id", None) if settings else None
    if not chat_id:
        await msg.reply_text("Вход в панель сейчас не настроен.")
        return

    try:
        member = await context.bot.get_chat_member(int(chat_id), user.id)
        is_admin = member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception as e:  # noqa: BLE001
        log.warning("panel_login: get_chat_member chat=%s user=%s: %s", chat_id, user.id, e)
        await msg.reply_text("Не удалось проверить ваши права в группе, попробуйте чуть позже.")
        return

    label = f"@{user.username}" if user.username else (user.full_name or str(user.id))
    with lock:
        rec = codes.get(payload)
        if not rec or rec.get("exp", 0) < now:
            await msg.reply_text("Ссылка истекла, начните вход заново.")
            return
        rec["uid"] = user.id
        rec["user"] = label
        rec["status"] = "authorized" if is_admin else "denied"

    if is_admin:
        log.info("panel_login: подтверждён вход uid=%s %s", user.id, label)
        await msg.reply_text("✅ Вход в панель подтверждён. Вернитесь на страницу — она откроется автоматически.")
    else:
        log.warning("panel_login: отказ (не админ) uid=%s %s", user.id, label)
        await msg.reply_text("⛔ Доступ к панели только для администраторов группы.")
