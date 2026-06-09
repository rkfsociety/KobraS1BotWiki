"""Главные обработчики: on_error, on_any_update, on_message."""
from __future__ import annotations

import logging
import time
import traceback
from collections import deque

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.admin_access import user_exempt_from_wiki_reply_spam_limits
from app.bot.clarify import (
    _maybe_handle_clarification_followup,
    _maybe_handle_clarify_correction_followup,
    _reply_is_expected_by_bot,
    _reply_no_guide_for_model,
    _try_send_error_code_clarify,
    _try_send_printer_clarify,
)
from app.bot.decision_log import log_seen_message, log_skip
from app.bot.design_replies import _maybe_reply_printer_design_vs_question
from app.bot.error_codes_wiki import _error_code_candidates, _pick_error_code_doc
from app.bot.error_display import _format_error_code_info_ru
from app.bot.i18n import _detect_user_lang, _t, format_wiki_card
from app.bot.missed_questions import add_missed_question
from app.bot.ops_notify import notify_ops
from app.bot.reply_access import chat_topic_in_allowed_lists, should_process_incoming_wiki_message
from app.bot.reply_logging import add_to_recent_replies, log_bot_reply_for_message
from app.bot.review_mention import reply_for_user
from app.bot.stores import _record_bot_answer_context
from app.bot.telegram_log_mirror import LOG_MIRROR_TEXT_MAX
from app.bot.text_heuristics import (
    _extract_error_code,
    _is_conversational_chatter,
    _is_error_code_query,
    _is_generic_help_without_context,
    _is_marketplace_promo_message,
    _model_slug_hints,
    _topic_is_marketplace_commerce_intent,
)
from app.bot.user_context import (
    enrich_query as _enrich_ctx_query,
    record_bot_answer as _record_bot_ans,
    record_user_message as _record_user_msg,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable, _search_best_with_model_bias
from app.error_codes_catalog import ErrorCodeInfo
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiIndex

from ._utils import _is_triggered_message, _trigger_source, _try_reply_manual_qa


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

    # Контекст пользователя: запись сообщения + обогащение запроса контекстом диалога.
    _ctx_uid = msg.from_user.id if msg.from_user else None

    if _ctx_uid is not None:
        _record_user_msg(context.application.bot_data, user_id=_ctx_uid, chat_id=chat_id, text=text)
        _ctx_text = _enrich_ctx_query(context.application.bot_data, user_id=_ctx_uid, chat_id=chat_id, query=text)
    else:
        _ctx_text = text

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
        logging.info(
            "Входящее сообщение chat=%s user=%s: %s",
            chat_id,
            msg.from_user.id if msg.from_user else "?",
            text[:LOG_MIRROR_TEXT_MAX],
        )

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
        variants = expand_queries(_ctx_text) if settings.ru_layer_enabled else [_ctx_text]
        best_doc, best_score = _search_best_with_model_bias(
            index, variants, context_text=_ctx_text, topic_for_keywords=_ctx_text
        )

    if not best_doc:
        if not is_err:
            add_missed_question(text=text, score=None, best_url=None, chat_id=chat_id)
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

        add_missed_question(
            text=text,
            score=best_score,
            best_url=best_doc.url if best_doc else None,
            chat_id=chat_id,
        )

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

    add_to_recent_replies(
        context.application.bot_data,
        question=text,
        answer=best_doc.title,
        url=url,
        source="wiki",
        chat_id=chat_id,
    )

    if _ctx_uid is not None:
        _record_bot_ans(
            context.application.bot_data,
            user_id=_ctx_uid,
            chat_id=chat_id,
            answer_text=best_doc.title,
            url=url,
        )

    # фиксируем отправку после успешного ответа
    rl["last_reply_ts_by_chat"][chat_id] = now
    q.append(now)
    last_url[url] = now
