"""Команда /update."""
from __future__ import annotations

import asyncio
import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.git_autopull import git_sync_from_remote, project_repo_root, schedule_restart_after_pull
from app.bot.i18n import _lang_from_message, _t
from app.bot.ops_notify import notify_ops
from app.bot.reply_logging import log_bot_reply_for_message

from ._utils import _deny_unless_admin_command_access


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
