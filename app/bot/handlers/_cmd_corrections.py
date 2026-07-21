"""Команды /error и /fix."""
from __future__ import annotations

import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.admin_activity import record_admin_action
from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.i18n import _lang_from_message, _t, format_wiki_card
from app.bot.reply_logging import log_bot_reply_for_message
from app.bot.stores import (
    _answer_ctx_key,
    _excluded_urls_for_query,
    _load_answer_ctx_store,
    _record_bot_answer_context,
    _remember_bad_answer,
    _remember_good_fix,
)
from app.bot.wiki_ranking import _response_wiki_url_acceptable, _search_best_with_model_bias_excluding
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiIndex

from ._utils import _deny_unless_admin_command_access


def _extract_url_arg(args: list[str]) -> str | None:
    for a in args or []:
        s = (a or "").strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
    return None


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

    if (
        not msg.reply_to_message
        or not msg.reply_to_message.from_user
        or bot_id is None
        or msg.reply_to_message.from_user.id != bot_id
    ):
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
        actor = msg.from_user
        if actor:
            record_admin_action(
                context.application.bot_data,
                action="delete_bot_msg",
                admin_id=actor.id,
                admin_username=actor.username,
                admin_first_name=actor.first_name,
                target_id=bad_mid,
                target_label=f"msg #{bad_mid}",
                chat_id=chat_id,
            )
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

    _record_bot_answer_context(
        context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=url
    )

    log_bot_reply_for_message(
        "cmd_error_retry", msg=msg, reply_text=retry_body, sent=sent, user_id=uid, score=best_score, url=url
    )


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

    if (
        not msg.reply_to_message
        or not msg.reply_to_message.from_user
        or bot_id is None
        or msg.reply_to_message.from_user.id != bot_id
    ):
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
        actor = msg.from_user
        if actor:
            record_admin_action(
                context.application.bot_data,
                action="delete_bot_msg",
                admin_id=actor.id,
                admin_username=actor.username,
                admin_first_name=actor.first_name,
                target_id=bad_mid,
                target_label=f"msg #{bad_mid}",
                chat_id=chat_id,
            )
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

    _record_bot_answer_context(
        context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=good_url
    )

    log_bot_reply_for_message("cmd_fix", msg=msg, reply_text=fix_body, sent=sent, user_id=uid, url=good_url)
