"""Команда /wiki."""
from __future__ import annotations

import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.clarify import _reply_no_guide_for_model, _try_send_printer_clarify
from app.bot.decision_log import log_skip
from app.bot.design_replies import _maybe_reply_printer_design_vs_question
from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.i18n import _lang_from_message, _t, format_wiki_card
from app.bot.reply_logging import log_bot_reply_for_message
from app.bot.review_mention import reply_for_user
from app.bot.text_heuristics import _is_error_code_query, _model_slug_hints
from app.bot.wiki_ranking import _response_wiki_url_acceptable, _search_best_with_model_bias
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiIndex

from ._utils import _deny_unless_admin_command_access, _try_reply_manual_qa


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
