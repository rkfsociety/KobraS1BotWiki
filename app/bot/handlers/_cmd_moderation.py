"""Команды модерации групп: бан, мут, предупреждения и работа с сообщениями."""
from __future__ import annotations

import logging
import re
import time

from telegram import ChatPermissions, Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.bot.admin_access import bot_has_moderation_right, user_has_moderation_command_access
from app.bot.admin_activity import record_admin_action
from app.bot.moderation import add_warning, clear_warnings, get_warnings, remove_warning
from app.bot.review_mention import record_outgoing_bot_message

log = logging.getLogger(__name__)

_DEFAULT_MUTE_SECONDS = 60 * 60
_MAX_MUTE_SECONDS = 30 * 24 * 60 * 60
_DURATION_RE = re.compile(r"^(\d+)([smhdw])$", re.IGNORECASE)


def _target_label(user) -> str:
    if user is None:
        return "неизвестный пользователь"
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    return (
        getattr(user, "full_name", None)
        or getattr(user, "first_name", None)
        or str(user.id)
    ).strip()


def _admin_label(user) -> str:
    return _target_label(user)


def _parse_duration(args: list[str]) -> tuple[int, str] | None:
    """Извлекает длительность из первого аргумента; без неё используется час."""
    if not args:
        return _DEFAULT_MUTE_SECONDS, ""
    match = _DURATION_RE.fullmatch(args[0].strip())
    if not match:
        return _DEFAULT_MUTE_SECONDS, " ".join(args).strip()
    amount = int(match.group(1))
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[match.group(2).lower()]
    seconds = amount * multiplier
    if seconds < 30 or seconds > _MAX_MUTE_SECONDS:
        return None
    return seconds, " ".join(args[1:]).strip()


def _reply_target(update: Update):
    msg = update.effective_message
    if msg is None or msg.reply_to_message is None:
        return None
    return msg.reply_to_message.from_user


def _target_message(update: Update):
    msg = update.effective_message
    return msg.reply_to_message if msg is not None else None


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    msg = update.effective_message
    sent = await msg.reply_text(text, **kwargs)
    chat = update.effective_chat
    if chat is not None:
        record_outgoing_bot_message(
            context.application.bot_data.get("chat_store"),
            sent,
            chat_id=chat.id,
            topic_id=getattr(msg, "message_thread_id", None),
            text=text,
            source="moderation",
            reply_to_id=getattr(msg, "message_id", None),
        )
    return sent


async def _allowed(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str) -> bool:
    if await user_has_moderation_command_access(update, context):
        return True
    log.info(
        "moderation denied command=/%s chat=%s user=%s",
        command,
        getattr(update.effective_chat, "id", None),
        getattr(update.effective_user, "id", None),
    )
    return False


async def _target_or_usage(update: Update, context: ContextTypes.DEFAULT_TYPE, *, require_user: bool = True):
    target = _reply_target(update) if require_user else _target_message(update)
    if target is None:
        await _reply(update, context,
            "Нужно ответить этой командой на сообщение пользователя: /ban, /mute, /warn и т.п."
            if require_user
            else "Нужно ответить этой командой на сообщение: /del, /pin или /unpin."
        )
        return None
    if require_user and (
        getattr(target, "is_bot", False)
        or target.id == getattr(update.effective_user, "id", None)
    ):
        await _reply(update, context, "Нельзя применить это действие к боту или к самому себе.")
        return None
    return target


async def _has_right(update: Update, context: ContextTypes.DEFAULT_TYPE, right: str) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    if await bot_has_moderation_right(context, chat.id, right):
        return True
    await _reply(update, context, "У бота нет необходимого права администратора для этой команды.")
    return False


async def _target_can_be_moderated(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    target,
    command: str,
) -> bool:
    """Не даёт командам ban/kick/mute затронуть владельца или админа группы."""
    chat = update.effective_chat
    if chat is None:
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, target.id)
    except Exception as exc:
        log.warning(
            "moderation target status check failed command=/%s chat=%s user=%s: %s",
            command,
            chat.id,
            target.id,
            exc,
        )
        await _reply(update, context,
            "Не удалось проверить статус цели. Команда отменена для безопасности."
        )
        return False

    status = getattr(member, "status", None)
    if status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
        await _reply(update, context,
            f"Нельзя применить /{command} к владельцу или администратору группы."
        )
        return False
    if status is None:
        await _reply(update, context,
            "Не удалось определить статус цели. Команда отменена для безопасности."
        )
        return False
    return True


async def _api_error(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str, exc: TelegramError) -> None:
    log.warning("moderation command failed command=/%s chat=%s: %s", command, getattr(update.effective_chat, "id", None), exc)
    await _reply(update, context, "Telegram не разрешил выполнить действие. Проверьте права бота и цель команды.")


def _record(context, update: Update, action: str, target) -> None:
    admin = update.effective_user
    chat = update.effective_chat
    if admin is None or chat is None:
        return
    record_admin_action(
        context.application.bot_data,
        action=action,
        admin_id=admin.id,
        admin_username=admin.username,
        admin_first_name=admin.first_name,
        target_id=getattr(target, "id", None),
        target_label=_target_label(target) if getattr(target, "id", None) is not None else None,
        chat_id=chat.id,
    )


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "ban"):
        return
    target = await _target_or_usage(update, context)
    if target is None or not await _target_can_be_moderated(update, context, target, "ban"):
        return
    if not await _has_right(update, context, "can_restrict_members"):
        return
    try:
        await context.bot.ban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            revoke_messages=False,
        )
    except TelegramError as exc:
        await _api_error(update, context, "ban", exc)
        return
    _record(context, update, "ban", target)
    await _reply(update, context, f"Пользователь {_target_label(target)} заблокирован.")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "unban"):
        return
    target = await _target_or_usage(update, context)
    if target is None or not await _has_right(update, context, "can_restrict_members"):
        return
    try:
        await context.bot.unban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            only_if_banned=True,
        )
    except TelegramError as exc:
        await _api_error(update, context, "unban", exc)
        return
    _record(context, update, "unban", target)
    await _reply(update, context, f"Пользователь {_target_label(target)} разблокирован.")


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет участника, оставляя ему возможность снова войти в группу."""
    if not await _allowed(update, context, "kick"):
        return
    target = await _target_or_usage(update, context)
    if target is None or not await _target_can_be_moderated(update, context, target, "kick"):
        return
    if not await _has_right(update, context, "can_restrict_members"):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=target.id, revoke_messages=False)
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=target.id, only_if_banned=True)
    except TelegramError as exc:
        await _api_error(update, context, "kick", exc)
        return
    _record(context, update, "kick", target)
    await _reply(update, context, f"Пользователь {_target_label(target)} удалён из чата.")


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "mute"):
        return
    target = await _target_or_usage(update, context)
    parsed = _parse_duration(list(context.args or []))
    if target is None or not await _target_can_be_moderated(update, context, target, "mute"):
        return
    if parsed is None:
        await _reply(update, context, "Срок мута: от 30 секунд до 30 дней. Пример: /mute 2h причина")
        return
    if not await _has_right(update, context, "can_restrict_members"):
        return
    seconds, reason = parsed
    until_date = int(time.time() + seconds)
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            permissions=ChatPermissions.no_permissions(),
            until_date=until_date,
        )
    except TelegramError as exc:
        await _api_error(update, context, "mute", exc)
        return
    _record(context, update, "restrict", target)
    suffix = f" Причина: {reason}" if reason else ""
    await _reply(update, context,
        f"Пользователь {_target_label(target)} замьючен на {_duration_label(seconds)}.{suffix}"
    )


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "unmute"):
        return
    target = await _target_or_usage(update, context)
    if target is None or not await _has_right(update, context, "can_restrict_members"):
        return
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target.id,
            permissions=_member_permissions(),
            until_date=None,
        )
    except TelegramError as exc:
        await _api_error(update, context, "unmute", exc)
        return
    _record(context, update, "unrestrict", target)
    await _reply(update, context, f"Пользователь {_target_label(target)} снова может писать.")


def _member_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_react_to_messages=True,
    )


def _duration_label(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} дн."
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    if seconds % 60 == 0:
        return f"{seconds // 60} мин."
    return f"{seconds} сек."


async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "warn"):
        return
    target = await _target_or_usage(update, context)
    if target is None:
        return
    admin = update.effective_user
    count = add_warning(
        context.application.bot_data,
        chat_id=update.effective_chat.id,
        user_id=target.id,
        admin_id=admin.id,
        admin_label=_admin_label(admin),
        reason=" ".join(context.args or []).strip(),
    )
    _record(context, update, "warn", target)
    await _reply(update, context, f"Пользователь {_target_label(target)} получил предупреждение №{count}.")


async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "unwarn"):
        return
    target = await _target_or_usage(update, context)
    if target is None:
        return
    count = remove_warning(context.application.bot_data, chat_id=update.effective_chat.id, user_id=target.id)
    if count == 0:
        await _reply(update, context, f"У пользователя {_target_label(target)} нет предупреждений.")
        return
    _record(context, update, "unwarn", target)
    await _reply(update, context, f"Последнее предупреждение снято. Осталось: {count}.")


async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "warnings"):
        return
    target = await _target_or_usage(update, context)
    if target is None:
        return
    warnings = get_warnings(context.application.bot_data, chat_id=update.effective_chat.id, user_id=target.id)
    if not warnings:
        await _reply(update, context, f"У пользователя {_target_label(target)} предупреждений нет.")
        return
    lines = [f"Предупреждения {_target_label(target)}: {len(warnings)}"]
    for index, warning in enumerate(warnings, 1):
        reason = warning.get("reason") or "без причины"
        lines.append(f"{index}. {reason}")
    await _reply(update, context, "\n".join(lines))


async def cmd_clearwarns(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "clearwarns"):
        return
    target = await _target_or_usage(update, context)
    if target is None:
        return
    count = clear_warnings(context.application.bot_data, chat_id=update.effective_chat.id, user_id=target.id)
    if count:
        _record(context, update, "unwarn", target)
    await _reply(update, context, f"Предупреждения {_target_label(target)} очищены: {count}.")


async def cmd_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "del"):
        return
    target = await _target_or_usage(update, context, require_user=False)
    if target is None or not await _has_right(update, context, "can_delete_messages"):
        return
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=target.message_id)
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.effective_message.message_id)
    except TelegramError as exc:
        await _api_error(update, context, "del", exc)
        return
    _record_message(context, update, "delete", target)


async def cmd_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "pin"):
        return
    target = await _target_or_usage(update, context, require_user=False)
    if target is None or not await _has_right(update, context, "can_pin_messages"):
        return
    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=target.message_id,
            disable_notification=True,
        )
    except TelegramError as exc:
        await _api_error(update, context, "pin", exc)
        return
    _record_message(context, update, "pin", target)
    await _reply(update, context, "Сообщение закреплено.")


async def cmd_unpin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _allowed(update, context, "unpin"):
        return
    target = await _target_or_usage(update, context, require_user=False)
    if target is None or not await _has_right(update, context, "can_pin_messages"):
        return
    try:
        await context.bot.unpin_chat_message(chat_id=update.effective_chat.id, message_id=target.message_id)
    except TelegramError as exc:
        await _api_error(update, context, "unpin", exc)
        return
    _record_message(context, update, "unpin", target)
    await _reply(update, context, "Сообщение откреплено.")


def _record_message(context, update: Update, action: str, message) -> None:
    """Записывает действие над сообщением, связывая его с автором, если он известен."""
    author = getattr(message, "from_user", None)
    _record(context, update, action, author)


__all__ = [
    "cmd_ban",
    "cmd_unban",
    "cmd_kick",
    "cmd_mute",
    "cmd_unmute",
    "cmd_warn",
    "cmd_unwarn",
    "cmd_warnings",
    "cmd_clearwarns",
    "cmd_del",
    "cmd_pin",
    "cmd_unpin",
]
