"""Базовые команды: /help, /id, /admincheck."""
from __future__ import annotations

import html
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from app.bot.admin_access import user_has_admin_command_access, user_id_is_developer
from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.help_text import format_help_message
from app.bot.i18n import _lang_from_message, _t
from app.bot.reply_logging import log_bot_reply_for_message

from ._utils import _deny_unless_admin_command_access


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


async def cmd_app(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Публикует в группе кнопку перехода в личный чат для запуска Mini App."""
    if not update.effective_message or not update.effective_chat:
        return

    if update.effective_chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if await _deny_unless_admin_command_access(update, context, command="app"):
        return

    bot_username = str(context.application.bot_data.get("bot_username") or "").strip().lstrip("@")
    if not bot_username:
        await update.effective_message.reply_text("Приложение пока недоступно: имя бота ещё не определено.")
        return

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📱 Открыть приложение", url=f"https://t.me/{bot_username}?start=app")]]
    )
    await update.effective_message.reply_text(
        "Открыть приложение поддержки можно в личном чате с ботом:",
        reply_markup=keyboard,
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
