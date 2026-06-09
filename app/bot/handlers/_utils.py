"""Общие вспомогательные функции для обработчиков."""
from __future__ import annotations

import hashlib
import html
import logging
import time
from collections import deque

from telegram import Update
from telegram.constants import ChatType, MessageEntityType, ParseMode
from telegram.ext import ContextTypes

from app.bot.admin_access import user_exempt_from_wiki_reply_spam_limits, user_has_admin_command_access
from app.bot.clarify import _reply_is_expected_by_bot
from app.bot.decision_log import log_skip
from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.i18n import _t
from app.bot.manual_qa import find_manual_qa_answer
from app.bot.reply_logging import add_to_recent_replies
from app.bot.review_mention import reply_for_user
from app.bot.stores import _record_bot_answer_context
from app.bot.user_context import record_bot_answer as _record_bot_ans


async def _deny_unless_admin_command_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    command: str,
) -> bool:
    """
    Если пользователь не администратор чата (и не личка с ботом) — молча игнорируем команду.

    True = остановить обработку без какого-либо ответа в чат.
    """
    if await user_has_admin_command_access(update, context):
        return False

    settings = context.application.bot_data.get("settings")
    chat_id = update.effective_chat.id if update.effective_chat else None
    uid = update.effective_user.id if update.effective_user else None

    if settings is not None and getattr(settings, "log_decisions", False):
        log_skip(chat_id, "non_admin_command", msg=update.effective_message, user=uid, cmd=f"/{command}")

    return True


def _is_triggered_message(update: Update, *, bot_username: str | None, bot_id: int | None) -> bool:
    msg = update.effective_message

    if not msg:
        return False

    # В личке можно отвечать всегда
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        return True

    # Упоминание @username
    if bot_username and msg.entities:
        uname = bot_username.lower().lstrip("@")
        for ent in msg.entities:
            if ent.type == MessageEntityType.MENTION:
                part = (msg.text or "")[ent.offset : ent.offset + ent.length]
                if part.lower().lstrip("@") == uname:
                    return True

    return False


def _trigger_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Как сообщение попало к боту: лс / упоминание / reply-боту / авто-вопрос.

    Используется в логах bot_reply, чтобы при разборе ложных срабатываний
    было видно, ответил ли бот по своей инициативе (auto) или его позвали.
    """
    chat = update.effective_chat
    if chat and chat.type == ChatType.PRIVATE:
        return "private"
    bot_username = context.application.bot_data.get("bot_username")
    bot_id = context.application.bot_data.get("bot_id")
    if _is_triggered_message(update, bot_username=bot_username, bot_id=bot_id):
        return "mention"
    if _reply_is_expected_by_bot(update, context):
        return "reply"
    return "auto"


def _manual_qa_answer_to_html(answer: str) -> str:
    return "\n".join(html.escape(line) for line in (answer or "").splitlines())


async def _try_reply_manual_qa(
    update: Update,
    msg,
    *,
    context: ContextTypes.DEFAULT_TYPE,
    query_text: str,
    chat_id: int,
    uid: int | None,
    lang: str,
    settings,
    log_kind: str,
    rl: dict,
    apply_rate_limit: bool,
    ephemeral_slash_user_msg,
) -> bool:
    entries = context.application.bot_data.get("manual_qa_entries")

    if not isinstance(entries, list):
        return False

    hit = find_manual_qa_answer(entries, query_text)

    if not hit:
        return False

    ans, _ttl = hit

    now = time.time()

    spam_exempt = await user_exempt_from_wiki_reply_spam_limits(update, context)

    syn_url = f"manual:{hashlib.md5(ans.encode('utf-8', errors='ignore')).hexdigest()}"

    if apply_rate_limit:
        last_reply_ts = rl["last_reply_ts_by_chat"].get(chat_id, 0.0)

        if not spam_exempt and now - last_reply_ts < settings.cooldown_seconds:
            if settings.log_decisions:
                log_skip(chat_id, "cooldown", msg=msg)
            return True

        q: deque[float] = rl["reply_ts_by_chat"].setdefault(chat_id, deque())
        cutoff = now - 60.0

        while q and q[0] < cutoff:
            q.popleft()

        if not spam_exempt and len(q) >= settings.max_replies_per_minute:
            if settings.log_decisions:
                log_skip(chat_id, "rate_limit", msg=msg)
            return True

        last_url = rl["last_url_ts_by_chat"].setdefault(chat_id, {})
        last_url_ts = float(last_url.get(syn_url, 0.0))

        if not spam_exempt and now - last_url_ts < settings.duplicate_window_seconds:
            if settings.log_decisions:
                log_skip(chat_id, "duplicate", msg=msg)
            return True

    body = f"{_t(lang, 'manual_qa_header')}\n\n{_manual_qa_answer_to_html(ans)}"

    sent = await reply_for_user(
        msg,
        settings,
        body,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        log_kind=log_kind,
        log_user_id=uid,
    )

    _record_bot_answer_context(
        context=context,
        chat_id=chat_id,
        bot_message_id=sent.message_id,
        query=query_text,
        url=None,
    )

    add_to_recent_replies(
        context.application.bot_data,
        question=query_text,
        answer=ans,
        url="",
        source="manual_qa",
        chat_id=chat_id,
    )

    if uid is not None:
        _record_bot_ans(
            context.application.bot_data,
            user_id=uid,
            chat_id=chat_id,
            answer_text=ans,
        )

    if apply_rate_limit:
        q = rl["reply_ts_by_chat"].setdefault(chat_id, deque())
        last_url = rl["last_url_ts_by_chat"].setdefault(chat_id, {})
        rl["last_reply_ts_by_chat"][chat_id] = now
        q.append(now)
        last_url[syn_url] = now

    if ephemeral_slash_user_msg is not None:
        schedule_delete_slash_command_and_reply(
            context=context,
            user_msg=ephemeral_slash_user_msg,
            bot_msg=sent,
            wiki_base_url=settings.wiki_base_url,
            outgoing_text=body,
        )

    return True
