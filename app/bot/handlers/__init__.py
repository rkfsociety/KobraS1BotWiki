"""Пакет обработчиков Telegram-бота."""
from ._cmd_basic import cmd_admincheck, cmd_app, cmd_help, cmd_id
from ._cmd_corrections import cmd_error, cmd_fix
from ._cmd_qa import cmd_qaadd, cmd_qadel, cmd_qalist
from ._cmd_status import cmd_ping, cmd_stats, cmd_status
from ._cmd_update import cmd_update
from ._cmd_wiki import cmd_wiki
from ._cmd_moderation import (
    cmd_ban,
    cmd_clearwarns,
    cmd_del,
    cmd_kick,
    cmd_mute,
    cmd_pin,
    cmd_unban,
    cmd_unmute,
    cmd_unpin,
    cmd_unwarn,
    cmd_warn,
    cmd_warnings,
)
from ._admin_activity import on_chat_member_updated, on_left_chat_member_service, on_pinned_message
from ._on_message import on_any_update, on_error, on_message
from ._routing import on_channel_command

__all__ = [
    "cmd_admincheck",
    "cmd_app",
    "cmd_error",
    "cmd_fix",
    "cmd_help",
    "cmd_id",
    "cmd_ping",
    "cmd_qaadd",
    "cmd_qadel",
    "cmd_qalist",
    "cmd_status",
    "cmd_stats",
    "cmd_update",
    "cmd_wiki",
    "cmd_ban",
    "cmd_clearwarns",
    "cmd_del",
    "cmd_kick",
    "cmd_mute",
    "cmd_pin",
    "cmd_unban",
    "cmd_unmute",
    "cmd_unpin",
    "cmd_unwarn",
    "cmd_warn",
    "cmd_warnings",
    "on_any_update",
    "on_channel_command",
    "on_chat_member_updated",
    "on_error",
    "on_left_chat_member_service",
    "on_message",
    "on_pinned_message",
]
