"""Обработчики Telegram: команды и входящие сообщения."""
from __future__ import annotations

import asyncio
import html
import logging
import time
from collections import deque

from telegram import Update
from telegram.constants import ChatType, MessageEntityType, ParseMode
from telegram.ext import ContextTypes

from app.bot.admin_access import user_exempt_from_wiki_reply_spam_limits, user_has_admin_command_access
from app.bot.clarify import (
    _reply_no_guide_for_model,
    _maybe_handle_clarification_followup,
    _maybe_handle_clarify_correction_followup,
    _reply_is_expected_by_bot,
    _try_send_error_code_clarify,
    _try_send_printer_clarify,
)
from app.bot.design_replies import _maybe_reply_printer_design_vs_question
from app.bot.error_codes_wiki import _error_code_candidates, _pick_error_code_doc
from app.bot.error_display import _format_error_code_info_ru
from app.bot.help_text import format_help_message
from app.bot.i18n import _detect_user_lang, _lang_from_message, _t
from app.bot.reply_logging import _log_bot_reply
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
    _is_error_code_query,
    _is_generic_help_without_context,
    _model_slug_hints,
)
from app.bot.wiki_ranking import (
    _response_wiki_url_acceptable,
    _search_best_with_model_bias,
    _search_best_with_model_bias_excluding,
)
from app.error_codes_catalog import ErrorCodeInfo
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiIndex


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
        logging.info("skip chat=%s user=%s reason=non_admin_command cmd=/%s", chat_id, uid, command)
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


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))
    is_admin = await user_has_admin_command_access(update, context)
    raw_u = context.application.bot_data.get("bot_username") or ""
    body = format_help_message(lang=lang, is_admin=is_admin, bot_username=str(raw_u))
    await msg.reply_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    uid = msg.from_user.id if msg.from_user else None
    _log_bot_reply("cmd_help", update.effective_chat.id, uid, admin=str(is_admin).lower())


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_message:
        return
    if await _deny_unless_admin_command_access(update, context, command="id"):
        return
    chat = update.effective_chat
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    text = (
        _t(lang, "cmd_id") + "\n"
        f"<code>{chat.id}</code>\n"
        f"{html.escape(_t(lang, 'cmd_type'))}: <code>{html.escape(chat.type)}</code>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    uid = msg.from_user.id if msg.from_user else None
    _log_bot_reply("cmd_id", update.effective_chat.id, uid)


async def cmd_wiki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    if await _deny_unless_admin_command_access(update, context, command="wiki"):
        return
    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    query = " ".join(context.args or []).strip()
    uid = msg.from_user.id if msg.from_user else None
    chat_id = update.effective_chat.id
    if not query:
        await msg.reply_text(_t(lang, "wiki_usage"), disable_web_page_preview=True)
        _log_bot_reply("cmd_wiki_usage", chat_id, uid)
        return

    if await _maybe_reply_printer_design_vs_question(
        msg,
        question=query,
        chat_id=chat_id,
        settings=settings,
        user_id=uid,
    ):
        return

    variants = expand_queries(query) if settings.ru_layer_enabled else [query]
    best_doc, best_score = _search_best_with_model_bias(
        index, variants, context_text=query, topic_for_keywords=query
    )

    if not best_doc:
        await msg.reply_text(_t(lang, "wiki_nothing_found"), disable_web_page_preview=True)
        _log_bot_reply("cmd_wiki_not_found", chat_id, uid, query=query[:80])
        return

    if best_score < settings.min_score:
        await msg.reply_text(_t(lang, "wiki_low_conf"), disable_web_page_preview=True)
        _log_bot_reply("cmd_wiki_low_score", chat_id, uid, score=best_score, min_score=settings.min_score, url=best_doc.url)
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
    )
    if clarify_cmd in ("sent", "blocked"):
        return

    url = best_doc.url
    if not _response_wiki_url_acceptable(query, url):
        await _reply_no_guide_for_model(
            msg,
            context=context,
            chat_id=chat_id,
            settings=settings,
            user_id=uid,
            best_url=url,
            hints=_model_slug_hints(query),
        )
        return

    title = html.escape(best_doc.title)
    reply = (
        _t(lang, "found_in_wiki") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>"
    )
    await msg.reply_text(reply, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
    _log_bot_reply("cmd_wiki", chat_id, uid, score=best_score, url=url)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    if await _deny_unless_admin_command_access(update, context, command="ping"):
        return
    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    text = (
        _t(lang, "ping") + "\n"
        f"chat_id: <code>{update.effective_chat.id}</code>\n"
        f"wiki_docs: <code>{index.doc_count}</code>\n"
        f"QUESTIONS_ONLY: <code>{settings.questions_only}</code>\n"
        f"REQUIRE_TRIGGER: <code>{settings.require_trigger}</code>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    uid = msg.from_user.id if msg.from_user else None
    _log_bot_reply("cmd_ping", update.effective_chat.id, uid)


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
    
    is_allowed = is_chat_allowed or is_topic_allowed
    
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
    _log_bot_reply("cmd_status", chat_id, uid)
    
    # Удаляем сообщение пользователя и ответ бота через 10 секунд
    import asyncio
    async def delete_messages():
        try:
            await asyncio.sleep(10)
            await msg.delete()
            await reply_msg.delete()
        except Exception:
            pass  # Игнорируем ошибки удаления (сообщения могли быть уже удалены)
    
    asyncio.create_task(delete_messages())


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
        await msg.reply_text(_t(lang, "error_usage"), disable_web_page_preview=True)
        _log_bot_reply("cmd_error_usage", chat_id, uid)
        return

    bad_mid = msg.reply_to_message.message_id
    store = context.application.bot_data.setdefault("answer_ctx_store", _load_answer_ctx_store())
    item = store.get(_answer_ctx_key(chat_id, bad_mid)) if isinstance(store, dict) else None
    if not isinstance(item, dict) or not item.get("q"):
        await msg.reply_text(_t(lang, "unknown_reply_ctx"), disable_web_page_preview=True)
        _log_bot_reply("cmd_error_no_ctx", chat_id, uid, bad_mid=bad_mid)
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
        await msg.reply_text(_t(lang, "error_no_better"), disable_web_page_preview=True)
        _log_bot_reply("cmd_error_no_better", chat_id, uid, score=(best_score if best_doc else None), url=(best_doc.url if best_doc else None))
        return

    title = html.escape(best_doc.title)
    url = best_doc.url
    sent = await msg.reply_text(
        _t(lang, "error_retry") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    _record_bot_answer_context(context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=url)
    _log_bot_reply("cmd_error_retry", chat_id, uid, score=best_score, url=url)


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

    bot_id = context.application.bot_data.get("bot_id")
    if not msg.reply_to_message or not msg.reply_to_message.from_user or bot_id is None or msg.reply_to_message.from_user.id != bot_id:
        await msg.reply_text(_t(lang, "fix_usage_reply"), disable_web_page_preview=True)
        _log_bot_reply("cmd_fix_usage", chat_id, uid)
        return

    good_url = _extract_url_arg(list(context.args or []))
    if not good_url:
        await msg.reply_text(_t(lang, "fix_usage"), disable_web_page_preview=True)
        _log_bot_reply("cmd_fix_usage", chat_id, uid)
        return

    bad_mid = msg.reply_to_message.message_id
    store = context.application.bot_data.setdefault("answer_ctx_store", _load_answer_ctx_store())
    item = store.get(_answer_ctx_key(chat_id, bad_mid)) if isinstance(store, dict) else None
    if not isinstance(item, dict) or not item.get("q"):
        await msg.reply_text(_t(lang, "unknown_reply_ctx"), disable_web_page_preview=True)
        _log_bot_reply("cmd_fix_no_ctx", chat_id, uid, bad_mid=bad_mid)
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

    sent = await msg.reply_text(
        _t(lang, "fix_confirm") + "\n"
        f"<a href=\"{html.escape(good_url)}\">{html.escape(good_url)}</a>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    _record_bot_answer_context(context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=good_url)
    _log_bot_reply("cmd_fix", chat_id, uid, url=good_url)

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled error while processing update: %s", context.error)


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
    message_thread_id = update.effective_message.message_thread_id if update.effective_message else None
    
    # Проверка разрешённых чатов и тем
    # Бот отвечает только если чат или тема в списке разрешённых (или списки не заданы)
    allowed_chats = settings.allowed_chat_ids
    allowed_topics = settings.allowed_topic_ids
    
    # Для on_message используем тот же подход: если message_thread_id=None в форуме,
    # это может быть общая тема General, но мы всё равно считаем topic_id=None
    actual_topic_id = message_thread_id
    
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
    
    # Если списки заданы — проверяем, что хотя бы одно условие выполнено
    # Если ни один список не задан — бот работает везде (старое поведение)
    if allowed_chats is not None or allowed_topics is not None:
        if not (is_chat_allowed or is_topic_allowed):
            if settings.log_decisions:
                logging.info(
                    "skip chat=%s topic=%s reason=not_in_allowed_lists",
                    chat_id,
                    message_thread_id
                )
            return
    
    msg = update.effective_message
    if not msg:
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

    # Базовая диагностика: если включено LOG_DECISIONS — логируем факт получения сообщения.
    if settings.log_decisions:
        uid = msg.from_user.id if msg.from_user else "?"
        rmid = msg.reply_to_message.message_id if msg.reply_to_message else None
        rfrom = msg.reply_to_message.from_user.id if (msg.reply_to_message and msg.reply_to_message.from_user) else None
        logging.info(
            "seen chat=%s user=%s has_reply=%s reply_mid=%s reply_from=%s text=%s",
            chat_id,
            uid,
            str(bool(msg.reply_to_message)).lower(),
            rmid,
            rfrom,
            text[:120],
        )

    # Если это reply на уточняющий вопрос бота — обработаем отдельно;
    # затем — поправка модели reply на любой ответ бота в той же «сессии».
    if settings.clarify_enabled:
        handled = await _maybe_handle_clarification_followup(update, context)
        if handled:
            return
        if await _maybe_handle_clarify_correction_followup(update, context):
            return

    if settings.log_all_messages:
        logging.info("Входящее сообщение chat=%s user=%s: %s", chat_id, msg.from_user.id if msg.from_user else "?", text[:200])

    # В группах отвечаем только если к нам обратились (упоминание) или это ожидаемый reply на уточнение.
    if settings.require_trigger:
        bot_username = context.application.bot_data.get("bot_username")
        bot_id = context.application.bot_data.get("bot_id")
        if not _is_triggered_message(update, bot_username=bot_username, bot_id=bot_id) and not _reply_is_expected_by_bot(update, context):
            if settings.log_decisions:
                logging.info("skip chat=%s reason=not_triggered", chat_id)
            return

    # Не отвечаем на команды и свои же/сервисные сообщения.
    if text.startswith("/"):
        return

    if settings.questions_only and not index.looks_like_question(text):
        if settings.log_decisions:
            logging.info("skip chat=%s reason=not_a_question", chat_id)
        return

    # Короткий "help" без контекста — просим уточнить, вместо бессмысленного поиска.
    if _is_generic_help_without_context(text):
        await msg.reply_text(
            _t(lang, "generic_help"),
            disable_web_page_preview=True,
        )
        _log_bot_reply("generic_help_clarify", chat_id, msg.from_user.id if msg.from_user else None)
        return

    if await _maybe_reply_printer_design_vs_question(
        msg,
        question=text,
        chat_id=chat_id,
        settings=settings,
        user_id=msg.from_user.id if msg.from_user else None,
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
                sent = await msg.reply_text(
                    formatted,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                _record_bot_answer_context(
                    context=context,
                    chat_id=chat_id,
                    bot_message_id=sent.message_id,
                    query=text,
                    url=None,
                )
                _log_bot_reply("error_code_text", chat_id, msg.from_user.id if msg.from_user else None, code=code)
                return
            if settings.log_decisions:
                logging.info("skip chat=%s reason=error_code_not_found code=%s", chat_id, code)
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
                logging.info("skip chat=%s reason=error_code_ambiguous code=%s", chat_id, code)
            return
    else:
        variants = expand_queries(text) if settings.ru_layer_enabled else [text]
        best_doc, best_score = _search_best_with_model_bias(
            index, variants, context_text=text, topic_for_keywords=text
        )

    if not best_doc:
        if settings.log_decisions:
            if is_err and code:
                logging.info("skip chat=%s reason=error_code_not_found code=%s", chat_id, code)
            else:
                logging.info("skip chat=%s reason=no_results docs=%d", chat_id, index.doc_count)
        return
    if best_score < settings.min_score:
        # Для кодов ошибок: либо находим точную страницу по коду, либо молчим (без уточнений).
        if is_err:
            if settings.log_decisions:
                logging.info(
                    "skip chat=%s reason=error_code_not_found score=%d min=%d url=%s",
                    chat_id,
                    best_score,
                    settings.min_score,
                    best_doc.url,
                )
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
            logging.info("skip chat=%s reason=low_score score=%d min=%d url=%s", chat_id, best_score, settings.min_score, best_doc.url)
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
                logging.info(
                    "skip chat=%s reason=error_code_not_found url=%s",
                    chat_id,
                    url,
                )
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
            logging.info("skip chat=%s reason=duplicate url=%s", chat_id, url)
        return

    title = html.escape(best_doc.title)
    score = best_score

    reply = (
        _t(context.application.bot_data.get("last_user_lang") or "ru", "already_in_wiki") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(context.application.bot_data.get('last_user_lang') or 'ru', 'match').format(score=score))}</i>"
    )

    sent = await msg.reply_text(
        reply,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    uid_r = msg.from_user.id if msg.from_user else None
    _log_bot_reply("wiki", chat_id, uid_r, score=best_score, url=url)
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

