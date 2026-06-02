"""Обработчики Telegram: команды и входящие сообщения."""

from __future__ import annotations

import asyncio

import hashlib

import html

import logging

import re

import time

import traceback

from collections import deque

from telegram import Update

from telegram.constants import ChatType, MessageEntityType, ParseMode

from telegram.ext import ContextTypes

from app.bot.admin_access import (

    user_exempt_from_wiki_reply_spam_limits,

    user_has_admin_command_access,

    user_id_is_developer,

)

from app.bot.clarify import (

    _reply_no_guide_for_model,

    _maybe_handle_clarification_followup,

    _maybe_handle_clarify_correction_followup,

    _reply_is_expected_by_bot,

    _try_send_error_code_clarify,

    _try_send_printer_clarify,

)

from app.bot.design_replies import _maybe_reply_printer_design_vs_question

from app.bot.ephemeral import schedule_delete_slash_command_and_reply

from app.bot.git_autopull import git_ping_compare_with_remote, git_sync_from_remote, project_repo_root, schedule_restart_after_pull

from app.bot.help_text import format_help_message

from app.bot.error_codes_wiki import _error_code_candidates, _pick_error_code_doc

from app.bot.error_display import _format_error_code_info_ru

from app.bot.manual_qa import (

    add_manual_qa_entry,

    delete_manual_qa_by_index,

    find_manual_qa_answer,

    try_git_push_manual_qa,

)

from app.bot.ops_notify import notify_ops

from app.bot.i18n import _detect_user_lang, _lang_from_message, _t, format_wiki_card

from app.bot.reply_logging import log_bot_reply_for_message

from app.bot.telegram_log_mirror import LOG_MIRROR_TEXT_MAX

from app.bot.decision_log import log_seen_message, log_skip

from app.bot.reply_access import chat_topic_in_allowed_lists, should_process_incoming_wiki_message

from app.bot.review_mention import reply_for_user

from app.bot.stores import (

    _answer_ctx_key,

    _excluded_urls_for_query,

    _load_answer_ctx_store,

    _remember_bad_answer,

    _remember_good_fix,

    _record_bot_answer_context,

)

from app.bot.text_heuristics import (

    _extract_error_code,

    _is_conversational_chatter,

    _is_error_code_query,

    _is_generic_help_without_context,

    _is_marketplace_promo_message,

    _topic_is_marketplace_commerce_intent,

    _model_slug_hints,

    _needs_model_clarification,

)

from app.bot.wiki_ranking import (

    _response_wiki_url_acceptable,

    _search_best_with_model_bias,

    _search_best_with_model_bias_excluding,

)

from app.error_codes_catalog import ErrorCodeInfo

from app.ru_layer import expand_queries

from app.web_wiki_index import WebWikiIndex

# CommandHandler в PTB не обрабатывает channel_post — маршрутизируем вручную (см. lifecycle.py).

_CHANNEL_COMMAND_HANDLERS: dict[str, object] = {}

def _register_channel_commands() -> None:

    if _CHANNEL_COMMAND_HANDLERS:

        return

    _CHANNEL_COMMAND_HANDLERS.update(

        {

            "help": cmd_help,

            "id": cmd_id,

            "admincheck": cmd_admincheck,

            "wiki": cmd_wiki,

            "ping": cmd_ping,

            "status": cmd_status,

            "error": cmd_error,

            "fix": cmd_fix,

            "qaadd": cmd_qaadd,

            "qalist": cmd_qalist,

            "qadel": cmd_qadel,

            "update": cmd_update,

        }

    )

async def on_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    """Команды в Telegram-канале (паблик): апдейты приходят как channel_post, не message."""

    _register_channel_commands()

    msg = update.effective_message

    if not msg or not msg.text:

        return

    head = (msg.text.split(maxsplit=1)[0] if msg.text else "").strip()

    if not head.startswith("/"):

        return

    cmd = head.split("@", 1)[0][1:].lower()

    handler = _CHANNEL_COMMAND_HANDLERS.get(cmd)

    if handler is None:

        return

    await handler(update, context)  # type: ignore[misc]

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

    return "<br>".join(html.escape(line) for line in (answer or "").splitlines())

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

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    msg = update.effective_message

    settings = context.application.bot_data["settings"]

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    is_admin = await user_has_admin_command_access(update, context)

    raw_u = context.application.bot_data.get("bot_username") or ""

    body = format_help_message(lang=lang, is_admin=is_admin, bot_username=str(raw_u))

    try:

        sent = await msg.reply_text(body, disable_web_page_preview=True)

    except Exception as e:

        logging.warning("cmd_help: reply failed chat=%s: %s", msg.chat_id, e)

        sent = await msg.reply_text(

            "Справка временно недоступна. Попробуйте /ping или /status.",

            disable_web_page_preview=True,

        )

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=body,

    )

    uid = msg.from_user.id if msg.from_user else None

    log_bot_reply_for_message(
        "cmd_help", msg=msg, reply_text=body, sent=sent, user_id=uid, admin=str(is_admin).lower()
    )

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_chat or not update.effective_message:

        return

    if await _deny_unless_admin_command_access(update, context, command="id"):

        return

    chat = update.effective_chat

    msg = update.effective_message

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    tid = getattr(msg, "message_thread_id", None)

    parts = [

        _t(lang, "cmd_id") + "\n"

        f"<code>{chat.id}</code>\n"

        f"{html.escape(_t(lang, 'cmd_type'))}: <code>{html.escape(str(chat.type))}</code>",

    ]

    if tid is not None:

        parts.append(f"{html.escape(_t(lang, 'cmd_topic_id'))}: <code>{tid}</code>")

    text = "\n".join(parts)

    sent = await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    settings = context.application.bot_data["settings"]

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=text,

    )

    uid = msg.from_user.id if msg.from_user else None

    log_bot_reply_for_message("cmd_id", msg=msg, reply_text=text, sent=sent, user_id=uid)

async def cmd_admincheck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    """Диагностика: как Telegram видит роль пользователя в чате и как бот трактует доступ к служебным командам."""

    if not update.effective_chat or not update.effective_message or not update.effective_user:

        return

    if await _deny_unless_admin_command_access(update, context, command="admincheck"):

        return

    chat = update.effective_chat

    msg = update.effective_message

    user = update.effective_user

    settings = context.application.bot_data["settings"]

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    lines = [_t(lang, "admincheck_header"), ""]

    if chat.type == ChatType.PRIVATE:

        lines.append(_t(lang, "admincheck_private"))

    elif chat.type == ChatType.CHANNEL:

        lines.append(_t(lang, "admincheck_channel"))

    else:

        lines.append(_t(lang, "admincheck_chat").format(chat_id=chat.id, chat_type=str(chat.type)))

        try:

            member = await context.bot.get_chat_member(chat.id, user.id)

            status = getattr(member.status, "value", None) or str(member.status)

        except Exception as e:

            status = _t(lang, "admincheck_member_fail").format(reason=str(e)[:200])

        lines.append(_t(lang, "admincheck_telegram").format(status=status))

    uname = f" @{user.username}" if user.username else ""

    lines.append("")

    lines.append(_t(lang, "admincheck_user").format(user_id=user.id, username=uname))

    yn_dev = _t(lang, "word_yes") if user_id_is_developer(user.id, settings) else _t(lang, "word_no")

    lines.append(_t(lang, "admincheck_developer").format(yesno=yn_dev))

    has_cmd = await user_has_admin_command_access(update, context)

    yn_cmd = _t(lang, "word_yes") if has_cmd else _t(lang, "word_no")

    lines.append(_t(lang, "admincheck_bot_access").format(yesno=yn_cmd))

    lines.append("")

    lines.append(_t(lang, "admincheck_footer"))

    body = "\n".join(lines)

    sent = await msg.reply_text(body, disable_web_page_preview=True)

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=body,

    )

    log_bot_reply_for_message("cmd_admincheck", msg=msg, reply_text=body, sent=sent, user_id=user.id)

async def cmd_wiki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="wiki"):

        return

    settings = context.application.bot_data["settings"]

    index: WebWikiIndex = context.application.bot_data["wiki_index"]

    msg = update.effective_message

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    raw_cmd = (msg.text or msg.caption or "").replace("\r\n", "\n")

    query = re.sub(r"^/wiki(?:@[\w]+)?\s*", "", raw_cmd, count=1, flags=re.I).strip()

    uid = msg.from_user.id if msg.from_user else None

    chat_id = update.effective_chat.id

    if not query:

        ut = _t(lang, "wiki_usage")

        sent = await msg.reply_text(ut, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=ut,

        )

        log_bot_reply_for_message("cmd_wiki_usage", msg=msg, reply_text=ut, sent=sent, user_id=uid)

        return

    rl = context.application.bot_data.setdefault(

        "rate_limit",

        {

            "last_reply_ts_by_chat": {},

            "reply_ts_by_chat": {},

            "last_url_ts_by_chat": {},

        },

    )

    # Точный ручной ответ (FAQ) важнее уточнения модели: куратор уже решил, что отвечать.
    if await _try_reply_manual_qa(

        update,

        msg,

        context=context,

        query_text=query,

        chat_id=chat_id,

        uid=uid,

        lang=lang,

        settings=settings,

        log_kind="manual_qa_cmd_wiki",

        rl=rl,

        apply_rate_limit=False,

        ephemeral_slash_user_msg=msg,

    ):

        return

    sent_pd = await _maybe_reply_printer_design_vs_question(

        msg,

        question=query,

        chat_id=chat_id,

        settings=settings,

        user_id=uid,

    )

    if sent_pd is not None:

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent_pd,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=sent_pd.text or "",

        )

        return

    variants = expand_queries(query) if settings.ru_layer_enabled else [query]

    best_doc, best_score = _search_best_with_model_bias(

        index, variants, context_text=query, topic_for_keywords=query

    )

    if not best_doc:

        nf = _t(lang, "wiki_nothing_found")

        sent = await msg.reply_text(nf, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=nf,

        )

        log_bot_reply_for_message(
            "cmd_wiki_not_found", msg=msg, reply_text=nf, sent=sent, user_id=uid, query=query[:80]
        )

        return

    if best_score < settings.min_score:

        lc = _t(lang, "wiki_low_conf")

        sent = await msg.reply_text(lc, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=lc,

        )

        log_bot_reply_for_message(
            "cmd_wiki_low_score",
            msg=msg,
            reply_text=lc,
            sent=sent,
            user_id=uid,
            score=best_score,
            min_score=settings.min_score,
            url=best_doc.url,
        )

        return

    clarify_cmd = await _try_send_printer_clarify(

        msg=msg,

        context=context,

        chat_id=chat_id,

        text=query,

        best_doc=best_doc,

        best_score=best_score,

        settings=settings,

        require_score_floor=False,

        score_floor=0,

        slash_command_ephemeral=True,

    )

    if clarify_cmd in ("sent", "blocked"):

        return

    url = best_doc.url

    if not _response_wiki_url_acceptable(query, url):

        # Слово «ошибка» без кода — не отвечаем «нет гайда» по разделу error-codes.

        if "/error-codes" in url.lower() and not _is_error_code_query(query):

            if settings.log_decisions:

                log_skip(chat_id, "error_codes_topic_mismatch", msg=msg, url=url)

            return

        sent_ng = await _reply_no_guide_for_model(

            msg,

            context=context,

            chat_id=chat_id,

            settings=settings,

            user_id=uid,

            best_url=url,

            hints=_model_slug_hints(query),

        )

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent_ng,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=sent_ng.text or "",

        )

        return

    reply = format_wiki_card(
        lang=lang,
        header_key="found_in_wiki",
        title=best_doc.title,
        url=url,
        score=best_score,
    )

    await reply_for_user(
        msg,
        settings,
        reply,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
        log_kind="cmd_wiki",
        log_extra={"score": best_score, "url": url},
        log_user_id=uid,
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="ping"):

        return

    settings = context.application.bot_data["settings"]

    index: WebWikiIndex = context.application.bot_data["wiki_index"]

    msg = update.effective_message

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    repo = project_repo_root()

    remote = settings.git_autopull_remote

    branch = settings.git_autopull_branch

    cache_key = f"{remote}/{branch}"

    ping_git_cache: dict = context.application.bot_data.setdefault("ping_git_cache", {})

    now = time.time()

    ttl = 60.0

    ent = ping_git_cache.get(cache_key)

    if isinstance(ent, dict) and now - float(ent.get("ts", 0)) < ttl:

        local_f = ent.get("local")

        remote_f = ent.get("remote")

        upd = ent.get("upd")

        gerr = ent.get("err")

    else:

        local_f, remote_f, upd, gerr = await asyncio.to_thread(

            git_ping_compare_with_remote,

            repo=repo,

            remote=remote,

            branch=branch,

        )

        ping_git_cache[cache_key] = {"ts": now, "local": local_f, "remote": remote_f, "upd": upd, "err": gerr}

    git_lines: list[str] = []

    if local_f:

        git_lines.append(

            f"{html.escape(_t(lang, 'ping_commit_running'))}: <code>{html.escape(local_f)}</code>"

        )

    if gerr:

        git_lines.append(html.escape(_t(lang, "ping_git_fail").format(detail=gerr[:400])))

    elif remote_f is not None and upd is not None:

        git_lines.append(

            html.escape(_t(lang, "ping_commit_upstream").format(remote=remote, branch=branch))

            + ": <code>"

            + html.escape(remote_f)

            + "</code>"

        )

        if upd:

            git_lines.append(html.escape(_t(lang, "ping_update_suggest")))

        else:

            git_lines.append(

                html.escape(_t(lang, "ping_git_ok").format(remote=remote, branch=branch))

            )

    git_block = ("\n" + "\n".join(git_lines)) if git_lines else ""

    text = (

        _t(lang, "ping") + "\n"

        f"chat_id: <code>{update.effective_chat.id}</code>\n"

        f"wiki_docs: <code>{index.doc_count}</code>\n"

        f"QUESTIONS_ONLY: <code>{settings.questions_only}</code>\n"

        f"REQUIRE_TRIGGER: <code>{settings.require_trigger}</code>"

        + git_block

    )

    sent = await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=text,

    )

    uid = msg.from_user.id if msg.from_user else None

    log_bot_reply_for_message("cmd_ping", msg=msg, reply_text=text, sent=sent, user_id=uid)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="status"):

        return

    settings = context.application.bot_data["settings"]

    index: WebWikiIndex = context.application.bot_data["wiki_index"]

    msg = update.effective_message

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    chat_id = update.effective_chat.id

    message_thread_id = update.effective_message.message_thread_id if update.effective_message else None

    

    # Дополнительная диагностика: проверяем chat.type для групп с темами

    chat_type = update.effective_chat.type

    is_supergroup_with_topics = (

        chat_type == ChatType.SUPERGROUP 

        and getattr(update.effective_chat, 'is_forum', False)

    )

    

    # Альтернативный способ получить topic_id: если message_thread_id None,

    # но мы в форуме, возможно это общая тема (General)

    actual_topic_id = message_thread_id

    topic_source = "message_thread_id"

    

    # Если message_thread_id None, но чат является форумом, это может быть общая тема

    if message_thread_id is None and is_supergroup_with_topics:

        # В форумах Telegram общая тема "General" обычно имеет thread_id = 1

        # Но API может возвращать None для сообщений в General

        actual_topic_id = None  # Остаётся None, так как это действительно "общий чат" форума

        topic_source = "general_forum_topic"

    

    # Проверка разрешённых чатов и тем для /status (отвечает везде, но показывает статус доступа)

    allowed_chats = settings.allowed_chat_ids

    allowed_topics = settings.allowed_topic_ids

    

    # Специальная обработка: если allowed_topics содержит 0, это означает "только общая тема General"

    # В этом случае actual_topic_id должен быть None (что и есть для General)

    allow_general_only = allowed_topics is not None and 0 in allowed_topics

    

    is_chat_allowed = (allowed_chats is None) or (chat_id in allowed_chats)

    

    if allow_general_only:

        # Разрешаем только если message_thread_id is None (общая тема)

        is_topic_allowed = actual_topic_id is None

    else:

        # Обычная логика: разрешаем если topic_id в списке или список не задан

        is_topic_allowed = (allowed_topics is None) or (actual_topic_id is not None and actual_topic_id in allowed_topics)

    

    is_allowed = chat_topic_in_allowed_lists(

        allowed_chat_ids=allowed_chats,

        allowed_topic_ids=allowed_topics,

        chat_id=chat_id,

        topic_id=actual_topic_id,

    )

    

    bot_username = context.application.bot_data.get("bot_username")

    text = (

        _t(lang, "bot_status") + "\n"

        f"bot: <code>@{html.escape(str(bot_username or ''))}</code>\n"

        f"chat_id: <code>{chat_id}</code>\n"

        f"chat_type: <code>{chat_type}</code>\n"

        f"is_forum: <code>{str(getattr(update.effective_chat, 'is_forum', False)).lower()}</code>\n"

    )

    if actual_topic_id is not None:

        text += f"topic_id: <code>{actual_topic_id}</code> (source: {topic_source})\n"

    elif is_supergroup_with_topics:

        text += "topic_id: <code>(общая тема General)</code>\n"

    else:

        text += "topic_id: <code>(нет, сообщение не в теме)</code>\n"

    

    # Форматируем список разрешённых чатов/тем для отображения

    allowed_chats_str = ",".join(str(x) for x in sorted(allowed_chats)) if allowed_chats else "(не заданы)"

    allowed_topics_str = ",".join(str(x) for x in sorted(allowed_topics)) if allowed_topics else "(не заданы)"

    

    text += (

        f"ALLOWED_CHAT_IDS: <code>{allowed_chats_str}</code>\n"

        f"ALLOWED_TOPIC_IDS: <code>{allowed_topics_str}</code>\n"

        f"chat_allowed: <code>{str(is_chat_allowed).lower()}</code>\n"

        f"topic_allowed: <code>{str(is_topic_allowed).lower()}</code>\n"

        f"is_allowed: <code>{str(is_allowed).lower()}</code>\n"

        f"wiki_docs: <code>{index.doc_count}</code>\n"

        f"QUESTIONS_ONLY: <code>{str(settings.questions_only).lower()}</code>\n"

        f"REQUIRE_TRIGGER: <code>{str(settings.require_trigger).lower()}</code>\n"

        f"RU_LAYER_ENABLED: <code>{str(settings.ru_layer_enabled).lower()}</code>\n"

        f"CLARIFY_ENABLED: <code>{str(settings.clarify_enabled).lower()}</code>\n"

        f"CLARIFY_CORRECTION_MAX: <code>{settings.clarify_correction_max}</code>\n"

        f"CLARIFY_CORRECTION_TTL_SECONDS: <code>{settings.clarify_correction_ttl_seconds}</code>\n"

        f"LOG_DECISIONS: <code>{str(settings.log_decisions).lower()}</code>"

    )

    reply_msg = await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    uid = msg.from_user.id if msg.from_user else None

    log_bot_reply_for_message("cmd_status", msg=msg, reply_text=text, sent=reply_msg, user_id=uid)

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=reply_msg,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=text,

    )

async def cmd_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    """

    /error — использовать только reply на сообщение бота, чтобы:

    - удалить неверный ответ бота

    - перепоискать ответ

    - запомнить, что тот URL был неверным (локальное обучение)

    """

    if not update.effective_chat or not update.effective_message:

        return

    if await _deny_unless_admin_command_access(update, context, command="error"):

        return

    msg = update.effective_message

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    chat_id = update.effective_chat.id

    uid = msg.from_user.id if msg.from_user else None

    settings = context.application.bot_data["settings"]

    bot_id = context.application.bot_data.get("bot_id")

    if not msg.reply_to_message or not msg.reply_to_message.from_user or bot_id is None or msg.reply_to_message.from_user.id != bot_id:

        eu = _t(lang, "error_usage")

        sent = await msg.reply_text(eu, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=eu,

        )

        log_bot_reply_for_message("cmd_error_usage", msg=msg, reply_text=eu, sent=sent, user_id=uid)

        return

    bad_mid = msg.reply_to_message.message_id

    store = context.application.bot_data.setdefault("answer_ctx_store", _load_answer_ctx_store())

    item = store.get(_answer_ctx_key(chat_id, bad_mid)) if isinstance(store, dict) else None

    if not isinstance(item, dict) or not item.get("q"):

        ur = _t(lang, "unknown_reply_ctx")

        sent = await msg.reply_text(ur, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=ur,

        )

        log_bot_reply_for_message("cmd_error_no_ctx", msg=msg, reply_text=ur, sent=sent, user_id=uid, bad_mid=bad_mid)

        return

    query = str(item.get("q") or "").strip()

    bad_url = str(item.get("url") or "").strip() or None

    _remember_bad_answer(context=context, query=query, bad_url=bad_url)

    # Удаляем неверный ответ бота (если есть права)

    try:

        await context.bot.delete_message(chat_id=chat_id, message_id=bad_mid)

    except Exception:

        pass

    # Перепоиск

    index: WebWikiIndex = context.application.bot_data["wiki_index"]

    exclude = _excluded_urls_for_query(context=context, query=query)

    variants = expand_queries(query) if settings.ru_layer_enabled else [query]

    best_doc, best_score = _search_best_with_model_bias_excluding(

        index,

        variants,

        context=context,

        context_text=query,

        topic_for_keywords=query,

        exclude_urls=exclude,

        top_k=max(40, int(settings.top_k) * 20),

    )

    if not best_doc or best_score < settings.min_score or not _response_wiki_url_acceptable(query, best_doc.url):

        nb = _t(lang, "error_no_better")

        sent = await msg.reply_text(nb, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=nb,

        )

        log_bot_reply_for_message(
            "cmd_error_no_better",
            msg=msg,
            reply_text=nb,
            sent=sent,
            user_id=uid,
            score=(best_score if best_doc else None),
            url=(best_doc.url if best_doc else None),
        )

        return

    url = best_doc.url

    retry_body = format_wiki_card(
        lang=lang,
        header_key="error_retry",
        title=best_doc.title,
        url=url,
        score=best_score,
    )

    sent = await msg.reply_text(

        retry_body,

        parse_mode=ParseMode.HTML,

        disable_web_page_preview=False,

    )

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=retry_body,

    )

    _record_bot_answer_context(context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=url)

    log_bot_reply_for_message(
        "cmd_error_retry", msg=msg, reply_text=retry_body, sent=sent, user_id=uid, score=best_score, url=url
    )

def _extract_url_arg(args: list[str]) -> str | None:

    for a in args or []:

        s = (a or "").strip()

        if s.startswith("http://") or s.startswith("https://"):

            return s

    return None

async def cmd_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    """

    /fix <url> — reply на сообщение бота:

    - удаляет старое сообщение бота

    - отправляет "правильную" ссылку

    - запоминает: старый URL плохой, новый — предпочтительный для этого запроса

    """

    if not update.effective_chat or not update.effective_message:

        return

    if await _deny_unless_admin_command_access(update, context, command="fix"):

        return

    msg = update.effective_message

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    chat_id = update.effective_chat.id

    uid = msg.from_user.id if msg.from_user else None

    settings = context.application.bot_data["settings"]

    bot_id = context.application.bot_data.get("bot_id")

    if not msg.reply_to_message or not msg.reply_to_message.from_user or bot_id is None or msg.reply_to_message.from_user.id != bot_id:

        fur = _t(lang, "fix_usage_reply")

        sent = await msg.reply_text(fur, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=fur,

        )

        log_bot_reply_for_message("cmd_fix_usage", msg=msg, reply_text=fur, sent=sent, user_id=uid)

        return

    good_url = _extract_url_arg(list(context.args or []))

    if not good_url:

        fu = _t(lang, "fix_usage")

        sent = await msg.reply_text(fu, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=fu,

        )

        log_bot_reply_for_message("cmd_fix_usage", msg=msg, reply_text=fu, sent=sent, user_id=uid)

        return

    bad_mid = msg.reply_to_message.message_id

    store = context.application.bot_data.setdefault("answer_ctx_store", _load_answer_ctx_store())

    item = store.get(_answer_ctx_key(chat_id, bad_mid)) if isinstance(store, dict) else None

    if not isinstance(item, dict) or not item.get("q"):

        ur = _t(lang, "unknown_reply_ctx")

        sent = await msg.reply_text(ur, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=ur,

        )

        log_bot_reply_for_message("cmd_fix_no_ctx", msg=msg, reply_text=ur, sent=sent, user_id=uid, bad_mid=bad_mid)

        return

    query = str(item.get("q") or "").strip()

    bad_url = str(item.get("url") or "").strip() or None

    # учимся: старый URL плохой, новый — предпочтительный

    _remember_bad_answer(context=context, query=query, bad_url=bad_url)

    _remember_good_fix(context=context, query=query, good_url=good_url)

    try:

        await context.bot.delete_message(chat_id=chat_id, message_id=bad_mid)

    except Exception:

        pass

    fix_body = (

        _t(lang, "fix_confirm") + "\n"

        f"<a href=\"{html.escape(good_url)}\">{html.escape(good_url)}</a>"

    )

    sent = await msg.reply_text(

        fix_body,

        parse_mode=ParseMode.HTML,

        disable_web_page_preview=False,

    )

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=fix_body,

    )

    _record_bot_answer_context(context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=good_url)

    log_bot_reply_for_message("cmd_fix", msg=msg, reply_text=fix_body, sent=sent, user_id=uid, url=good_url)

async def cmd_qaadd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="qaadd"):

        return

    msg = update.effective_message

    settings = context.application.bot_data["settings"]

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    uid = msg.from_user.id if msg.from_user else None

    norm = (msg.text or msg.caption or "").replace("\r\n", "\n")

    body = re.sub(r"^/qaadd(?:@[\w]+)?\s*", "", norm, count=1, flags=re.I).strip()

    parts = body.split("\n---\n", 1)

    if len(parts) < 2:

        parts = re.split(r"\s*---\s*", body, maxsplit=1)

    if len(parts) < 2:

        usage = _t(lang, "qaadd_usage")

        sent = await msg.reply_text(usage, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=usage,

        )

        log_bot_reply_for_message("cmd_qaadd_usage", msg=msg, reply_text=usage, sent=sent, user_id=uid)

        return

    q_block, a_block = parts[0].strip(), parts[1].strip()

    key_parts = [p.strip() for p in q_block.split("|||") if p.strip()]

    if not key_parts or not a_block:

        usage = _t(lang, "qaadd_usage")

        sent = await msg.reply_text(usage, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=usage,

        )

        log_bot_reply_for_message("cmd_qaadd_usage", msg=msg, reply_text=usage, sent=sent, user_id=uid)

        return

    entries = context.application.bot_data.setdefault("manual_qa_entries", [])

    if not isinstance(entries, list):

        entries = []

        context.application.bot_data["manual_qa_entries"] = entries

    ok, detail = add_manual_qa_entry(

        entries=entries,

        raw_keys=key_parts,

        answer=a_block,

        title=key_parts[0],

    )

    if ok:

        detail_full = detail

        if settings.manual_qa_git_push:

            pok, pmsg = await asyncio.to_thread(try_git_push_manual_qa)

            detail_full = f"{detail}; GitHub: {pmsg}"

            if not pok:

                logging.warning("manual_qa git push: %s", pmsg)

        ok_body = _t(lang, "qaadd_ok").format(detail=html.escape(detail_full))

        sent = await msg.reply_text(ok_body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=ok_body,

        )

        log_bot_reply_for_message("cmd_qaadd", msg=msg, reply_text=ok_body, sent=sent, user_id=uid, keys=len(key_parts))

    else:

        fail = _t(lang, "qaadd_fail").format(reason=html.escape(detail))

        sent = await msg.reply_text(fail, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=fail,

        )

        log_bot_reply_for_message(
            "cmd_qaadd_fail", msg=msg, reply_text=fail, sent=sent, user_id=uid, reason=detail[:120]
        )

async def cmd_qalist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="qalist"):

        return

    msg = update.effective_message

    settings = context.application.bot_data["settings"]

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    uid = msg.from_user.id if msg.from_user else None

    entries = context.application.bot_data.get("manual_qa_entries")

    if not isinstance(entries, list) or not entries:

        sent = await msg.reply_text(_t(lang, "qalist_empty"), disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=_t(lang, "qalist_empty"),

        )

        empty_text = _t(lang, "qalist_empty")
        log_bot_reply_for_message("cmd_qalist_empty", msg=msg, reply_text=empty_text, sent=sent, user_id=uid)

        return

    lines = [_t(lang, "qalist_header")]

    for i, e in enumerate(entries[:40], start=1):

        if not isinstance(e, dict):

            continue

        ks = e.get("keys")

        if not isinstance(ks, list):

            continue

        keys_h = html.escape(", ".join(str(k) for k in ks[:8])[:220])

        tl = html.escape(str(e.get("title", ""))[:100])

        lines.append(f"{i}. <b>{tl}</b> — <code>{keys_h}</code>")

    body = "\n".join(lines)

    sent = await msg.reply_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    schedule_delete_slash_command_and_reply(

        context=context,

        user_msg=msg,

        bot_msg=sent,

        wiki_base_url=settings.wiki_base_url,

        outgoing_text=body,

    )

    log_bot_reply_for_message("cmd_qalist", msg=msg, reply_text=body, sent=sent, user_id=uid, n=len(entries))

async def cmd_qadel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="qadel"):

        return

    msg = update.effective_message

    settings = context.application.bot_data["settings"]

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    uid = msg.from_user.id if msg.from_user else None

    args = list(context.args or [])

    if not args:

        usage = _t(lang, "qadel_usage")

        sent = await msg.reply_text(usage, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=usage,

        )

        log_bot_reply_for_message("cmd_qadel_usage", msg=msg, reply_text=usage, sent=sent, user_id=uid)

        return

    try:

        n = int(str(args[0]).strip())

    except ValueError:

        usage = _t(lang, "qadel_usage")

        sent = await msg.reply_text(usage, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=usage,

        )

        log_bot_reply_for_message("cmd_qadel_usage", msg=msg, reply_text=usage, sent=sent, user_id=uid)

        return

    entries = context.application.bot_data.setdefault("manual_qa_entries", [])

    if not isinstance(entries, list):

        entries = []

        context.application.bot_data["manual_qa_entries"] = entries

    ok, reason = delete_manual_qa_by_index(entries=entries, one_based=n)

    if ok:

        detail_extra = ""

        if settings.manual_qa_git_push:

            pok, pmsg = await asyncio.to_thread(try_git_push_manual_qa)

            detail_extra = f"; GitHub: {pmsg}"

            if not pok:

                logging.warning("manual_qa git push: %s", pmsg)

        body = _t(lang, "qadel_ok").format(n=n) + html.escape(detail_extra)

        sent = await msg.reply_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=body,

        )

        log_bot_reply_for_message("cmd_qadel", msg=msg, reply_text=body, sent=sent, user_id=uid, n=n)

    else:

        body = _t(lang, "qadel_fail").format(reason=html.escape(reason))

        sent = await msg.reply_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=body,

        )

        log_bot_reply_for_message("cmd_qadel_fail", msg=msg, reply_text=body, sent=sent, user_id=uid, n=n)

async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message or not update.effective_chat:

        return

    if await _deny_unless_admin_command_access(update, context, command="update"):

        return

    msg = update.effective_message

    settings = context.application.bot_data["settings"]

    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    uid = msg.from_user.id if msg.from_user else None

    lock = context.application.bot_data.get("git_update_lock")

    if lock is None:

        lock = asyncio.Lock()

        context.application.bot_data["git_update_lock"] = lock

    async with lock:

        repo = project_repo_root()

        try:

            updated, gmsg = await asyncio.to_thread(

                git_sync_from_remote,

                repo=repo,

                remote=settings.git_autopull_remote,

                branch=settings.git_autopull_branch,

                hard_reset=settings.git_autopull_hard_reset,

            )

        except Exception as e:

            body = _t(lang, "update_fail").format(reason=html.escape(str(e)))

            sent = await msg.reply_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

            schedule_delete_slash_command_and_reply(

                context=context,

                user_msg=msg,

                bot_msg=sent,

                wiki_base_url=settings.wiki_base_url,

                outgoing_text=body,

            )

            log_bot_reply_for_message("cmd_update_exc", msg=msg, reply_text=body, sent=sent, user_id=uid)

            await notify_ops(context.application, f"/update: исключение при git\n{type(e).__name__}: {e}")

            return

        if not updated:

            if gmsg == "уже актуально":

                body = _t(lang, "update_uptodate")

            else:

                body = _t(lang, "update_fail").format(reason=html.escape(gmsg))

            sent = await msg.reply_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

            schedule_delete_slash_command_and_reply(

                context=context,

                user_msg=msg,

                bot_msg=sent,

                wiki_base_url=settings.wiki_base_url,

                outgoing_text=body,

            )

            log_bot_reply_for_message(
                "cmd_update_noop", msg=msg, reply_text=body, sent=sent, user_id=uid, detail=(gmsg or "")[:160]
            )

            if gmsg != "уже актуально":

                await notify_ops(context.application, f"/update: не обновлено\n{gmsg}")

            return

        ok_body = _t(lang, "update_ok").format(detail=html.escape(gmsg))

        sent = await msg.reply_text(ok_body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=ok_body,

        )

        log_bot_reply_for_message(
            "cmd_update_pull", msg=msg, reply_text=ok_body, sent=sent, user_id=uid, detail=gmsg
        )

        await schedule_restart_after_pull(

            application=context.application,

            git_pull_restart_state=context.application.bot_data["git_pull_restart_state"],

            restart_command=settings.git_restart_command,

            log_tag="cmd_update",

        )

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:

    logging.exception("Unhandled error while processing update: %s", context.error)

    try:

        app = context.application

        lines = ["Ошибка в обработчике (unhandled)"]

        if isinstance(update, Update):

            try:

                if update.effective_chat:

                    lines.append(f"chat_id={update.effective_chat.id}")

                if update.effective_user:

                    lines.append(f"user_id={update.effective_user.id}")

            except Exception:

                pass

        err = context.error

        if err is not None:

            lines.append(f"{type(err).__name__}: {err}")

            lines.append(traceback.format_exc())

        await notify_ops(app, "\n".join(lines))

    except Exception as e:

        logging.warning("ops_notify from on_error: %s", e)

async def on_any_update(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:

    """

    Диагностика: логируем факт получения любого update, чтобы понять

    приходит ли вообще обычный message в бота.

    """

    settings = context.application.bot_data.get("settings")

    if not settings or not getattr(settings, "log_decisions", False):

        return

    try:

        if isinstance(update, Update):

            chat = update.effective_chat

            m = update.effective_message

            if chat and m and not chat_topic_in_allowed_lists(

                allowed_chat_ids=settings.allowed_chat_ids,

                allowed_topic_ids=settings.allowed_topic_ids,

                chat_id=chat.id,

                topic_id=m.message_thread_id,

            ):

                return

            kind = (

                "message"

                if update.message

                else "edited_message"

                if update.edited_message

                else "channel_post"

                if update.channel_post

                else "other"

            )

            chat_id = update.effective_chat.id if update.effective_chat else "?"

            uid = update.effective_user.id if update.effective_user else "?"

            txt = None

            reply_mid = None

            reply_from = None

            m = update.effective_message

            if m:

                txt = m.text if m.text is not None else m.caption

                if m.reply_to_message:

                    reply_mid = m.reply_to_message.message_id

                    if m.reply_to_message.from_user:

                        reply_from = m.reply_to_message.from_user.id

            logging.info(

                "update kind=%s chat=%s user=%s has_reply=%s reply_mid=%s reply_from=%s text=%s",

                kind,

                chat_id,

                uid,

                str(bool(m and m.reply_to_message)).lower(),

                reply_mid,

                reply_from,

                (txt or "")[:80],

            )

        else:

            logging.info("update type=%s", type(update).__name__)

    except Exception:

        # не ломаем обработку апдейтов диагностикой

        pass

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    if not update.effective_message:

        return

    if not update.effective_chat:

        return

    settings = context.application.bot_data["settings"]

    index: WebWikiIndex = context.application.bot_data["wiki_index"]

    rl = context.application.bot_data.setdefault(

        "rate_limit",

        {

            "last_reply_ts_by_chat": {},

            "reply_ts_by_chat": {},

            "last_url_ts_by_chat": {},

        },

    )

    chat_id = update.effective_chat.id

    msg = update.effective_message

    topic_id = msg.message_thread_id

    ok, _reason = await should_process_incoming_wiki_message(

        context,

        settings,

        update.effective_chat,

        chat_id,

        topic_id,

    )

    if not ok:

        return

    # В группах часто вопросы прилетают как "text", но иногда как подпись к медиа.

    raw_text = msg.text if msg.text is not None else msg.caption

    if not raw_text:

        return

    text = raw_text.strip()

    if not text:

        return

    # Язык ответа: определяем по языку сообщения/пользователя.

    user_lang_code = msg.from_user.language_code if (msg.from_user and getattr(msg.from_user, "language_code", None)) else None

    lang = _detect_user_lang(text=text, user_lang_code=user_lang_code)

    context.application.bot_data["last_user_lang"] = lang

    # Если это reply на уточняющий вопрос бота — обработаем отдельно;

    # затем — поправка модели reply на любой ответ бота в той же «сессии».

    if settings.clarify_enabled:

        handled = await _maybe_handle_clarification_followup(update, context)

        if handled:

            return

        if await _maybe_handle_clarify_correction_followup(update, context):

            return

    # Базовая диагностика: после clarify (там логируется полный combined-текст).

    if settings.log_decisions:

        uid = msg.from_user.id if msg.from_user else "?"

        rmid = msg.reply_to_message.message_id if msg.reply_to_message else None

        rfrom = msg.reply_to_message.from_user.id if (msg.reply_to_message and msg.reply_to_message.from_user) else None

        log_seen_message(

            chat_id=chat_id,

            user_id=uid,

            msg=msg,

            has_reply=bool(msg.reply_to_message),

            reply_mid=rmid,

            reply_from=rfrom,

            text=text,

        )

    if settings.log_all_messages:

        logging.info("Входящее сообщение chat=%s user=%s: %s", chat_id, msg.from_user.id if msg.from_user else "?", text[:LOG_MIRROR_TEXT_MAX])

    # В группах: на вопросы отвечаем без @; @ или reply нужны для прочих сообщений (если REQUIRE_TRIGGER).

    if settings.require_trigger:

        bot_username = context.application.bot_data.get("bot_username")

        bot_id = context.application.bot_data.get("bot_id")

        triggered = _is_triggered_message(update, bot_username=bot_username, bot_id=bot_id) or _reply_is_expected_by_bot(

            update, context

        )

        if not triggered and not index.looks_like_question(text):

            if settings.log_decisions:

                log_skip(chat_id, "not_triggered", msg=msg)

            return

    # Не отвечаем на команды и свои же/сервисные сообщения.

    if text.startswith("/"):

        if settings.log_decisions:

            log_skip(chat_id, "slash_command", msg=msg)

        return

    if _is_marketplace_promo_message(text):

        if settings.log_decisions:

            log_skip(chat_id, "marketplace_promo", msg=msg)

        return

    if _topic_is_marketplace_commerce_intent(text):

        if settings.log_decisions:

            log_skip(chat_id, "marketplace_commerce", msg=msg)

        return

    if _is_conversational_chatter(text):

        if settings.log_decisions:

            log_skip(chat_id, "conversational_chatter", msg=msg)

        return

    if settings.questions_only and not index.looks_like_question(text):

        if settings.log_decisions:

            log_skip(chat_id, "not_a_question", msg=msg)

        return

    # Короткий "help" без контекста — просим уточнить, вместо бессмысленного поиска.

    if _is_generic_help_without_context(text):

        help_text = _t(lang, "generic_help")
        sent_help = await msg.reply_text(help_text, disable_web_page_preview=True)
        log_bot_reply_for_message(
            "generic_help_clarify",
            msg=msg,
            reply_text=help_text,
            sent=sent_help,
            user_id=msg.from_user.id if msg.from_user else None,
        )

        return

    if await _maybe_reply_printer_design_vs_question(

        msg,

        question=text,

        chat_id=chat_id,

        settings=settings,

        user_id=msg.from_user.id if msg.from_user else None,

    ):

        return

    # Точный ручной ответ (FAQ) важнее уточнения модели: куратор уже решил, что отвечать.
    if await _try_reply_manual_qa(

        update,

        msg,

        context=context,

        query_text=text,

        chat_id=chat_id,

        uid=msg.from_user.id if msg.from_user else None,

        lang=lang,

        settings=settings,

        log_kind="manual_qa_message",

        rl=rl,

        apply_rate_limit=True,

        ephemeral_slash_user_msg=None,

    ):

        return

    is_err = _is_error_code_query(text)

    code = _extract_error_code(text)

    if is_err and code:

        candidates = _error_code_candidates(index, code)

        if not candidates:

            # fallback: отдельный каталог ошибок из /en/error-codes + ручные доп. записи

            catalog: dict[str, ErrorCodeInfo] = context.application.bot_data.get("error_codes_catalog", {})

            info = catalog.get(code) if isinstance(catalog, dict) else None

            if info:

                formatted = await _format_error_code_info_ru(context=context, info=info)

                sent = await reply_for_user(
                    msg,
                    settings,
                    formatted,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    log_kind="error_code_text",
                    log_extra={"code": code},
                    log_user_id=msg.from_user.id if msg.from_user else None,
                )

                _record_bot_answer_context(

                    context=context,

                    chat_id=chat_id,

                    bot_message_id=sent.message_id,

                    query=text,

                    url=None,

                )

                return

            if settings.log_decisions:

                log_skip(chat_id, "error_code_not_found", msg=msg, code=code)

            return

        best_doc = _pick_error_code_doc(index, code, context_text=text)

        best_score = 100 if best_doc else -1

        if best_doc is None:

            if await _try_send_error_code_clarify(

                msg=msg,

                context=context,

                chat_id=chat_id,

                text=text,

                code=code,

                candidates=candidates,

                settings=settings,

            ):

                return

            # Если не смогли выбрать и уточнение не отправили — молчим.

            if settings.log_decisions:

                log_skip(chat_id, "error_code_ambiguous", msg=msg, code=code)

            return

    else:

        variants = expand_queries(text) if settings.ru_layer_enabled else [text]

        best_doc, best_score = _search_best_with_model_bias(

            index, variants, context_text=text, topic_for_keywords=text

        )

    if not best_doc:

        if settings.log_decisions:

            if is_err and code:

                log_skip(chat_id, "error_code_not_found", msg=msg, code=code)

            else:

                log_skip(chat_id, "no_results", msg=msg, docs=index.doc_count)

        return

    if best_score < settings.min_score:

        # Для кодов ошибок: либо находим точную страницу по коду, либо молчим (без уточнений).

        if is_err:

            if settings.log_decisions:

                log_skip(chat_id, "error_code_not_found", msg=msg, score=best_score, min=settings.min_score, url=best_doc.url)

            return

        clarify_low = await _try_send_printer_clarify(

            msg=msg,

            context=context,

            chat_id=chat_id,

            text=text,

            best_doc=best_doc,

            best_score=best_score,

            settings=settings,

            require_score_floor=True,

            score_floor=settings.clarify_min_score,

        )

        if clarify_low in ("sent", "blocked"):

            return

        if settings.log_decisions:

            log_skip(

                chat_id,

                "low_score",

                msg=msg,

                score=best_score,

                min=settings.min_score,

                url=best_doc.url,

            )

        return

    clarify_hi = await _try_send_printer_clarify(

        msg=msg,

        context=context,

        chat_id=chat_id,

        text=text,

        best_doc=best_doc,

        best_score=best_score,

        settings=settings,

        require_score_floor=False,

        score_floor=0,

    )

    if clarify_hi in ("sent", "blocked"):

        return

    url = best_doc.url

    if not _response_wiki_url_acceptable(text, url):

        # Для кодов ошибок не шлём "нет гайда" — просто молчим.

        if is_err:

            if settings.log_decisions:

                log_skip(chat_id, "error_code_not_found", msg=msg, url=url)

            return

        # Слово «ошибка» без кода — не отвечаем «нет гайда» по разделу error-codes.

        if "/error-codes" in url.lower() and not _is_error_code_query(text):

            if settings.log_decisions:

                log_skip(chat_id, "error_codes_topic_mismatch", msg=msg, url=url)

            return

        await _reply_no_guide_for_model(

            msg,

            context=context,

            chat_id=chat_id,

            settings=settings,

            user_id=msg.from_user.id if msg.from_user else None,

            best_url=url,

            hints=_model_slug_hints(text),

        )

        return

    # ---- антиспам (на чат); админы чата и allowlist — без ограничений ----

    now = time.time()

    spam_exempt = await user_exempt_from_wiki_reply_spam_limits(update, context)

    last_reply_ts = rl["last_reply_ts_by_chat"].get(chat_id, 0.0)

    if not spam_exempt and now - last_reply_ts < settings.cooldown_seconds:

        if settings.log_decisions:

            logging.info("skip chat=%s reason=cooldown", chat_id)

        return

    q: deque[float] = rl["reply_ts_by_chat"].setdefault(chat_id, deque())

    cutoff = now - 60.0

    while q and q[0] < cutoff:

        q.popleft()

    if not spam_exempt and len(q) >= settings.max_replies_per_minute:

        if settings.log_decisions:

            logging.info("skip chat=%s reason=rate_limit", chat_id)

        return

    last_url = rl["last_url_ts_by_chat"].setdefault(chat_id, {})

    last_url_ts = float(last_url.get(url, 0.0))

    if not spam_exempt and now - last_url_ts < settings.duplicate_window_seconds:

        if settings.log_decisions:

            log_skip(chat_id, "duplicate", msg=msg, url=url)

        return

    reply = format_wiki_card(
        lang=context.application.bot_data.get("last_user_lang") or "ru",
        header_key="already_in_wiki",
        title=best_doc.title,
        url=url,
        score=best_score,
    )

    sent = await reply_for_user(
        msg,
        settings,
        reply,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
        log_kind="wiki",
        log_extra={
            "score": best_score,
            "url": url,
            "trigger": _trigger_source(update, context),
            "model": "+".join(sorted(_model_slug_hints(text))) or None,
        },
        log_user_id=msg.from_user.id if msg.from_user else None,
    )

    _record_bot_answer_context(

        context=context,

        chat_id=chat_id,

        bot_message_id=sent.message_id,

        query=text,

        url=url,

    )

    # фиксируем отправку после успешного ответа

    rl["last_reply_ts_by_chat"][chat_id] = now

    q.append(now)

    last_url[url] = now

