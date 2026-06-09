"""Команды /qaadd, /qalist, /qadel."""
from __future__ import annotations

import asyncio
import html
import logging
import re

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.i18n import _lang_from_message, _t
from app.bot.manual_qa import add_manual_qa_entry, delete_manual_qa_by_index, try_git_push_manual_qa
from app.bot.reply_logging import log_bot_reply_for_message

from ._utils import _deny_unless_admin_command_access


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
