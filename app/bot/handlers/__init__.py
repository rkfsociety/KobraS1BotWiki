"""Пакет обработчиков Telegram-бота."""
from ._cmd_basic import cmd_admincheck, cmd_help, cmd_id
from ._cmd_corrections import cmd_error, cmd_fix
from ._cmd_qa import cmd_qaadd, cmd_qadel, cmd_qalist
from ._cmd_status import cmd_ping, cmd_status
from ._cmd_update import cmd_update
from ._cmd_wiki import cmd_wiki
from ._on_message import on_any_update, on_error, on_message
from ._routing import on_channel_command

__all__ = [
    "cmd_admincheck",
    "cmd_error",
    "cmd_fix",
    "cmd_help",
    "cmd_id",
    "cmd_ping",
    "cmd_qaadd",
    "cmd_qadel",
    "cmd_qalist",
    "cmd_status",
    "cmd_update",
    "cmd_wiki",
    "on_any_update",
    "on_channel_command",
    "on_error",
    "on_message",
]
