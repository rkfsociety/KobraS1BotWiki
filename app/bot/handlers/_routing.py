"""Маршрутизация команд в каналах (channel_post)."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ._cmd_basic import cmd_admincheck, cmd_help, cmd_id
from ._cmd_corrections import cmd_error, cmd_fix
from ._cmd_qa import cmd_qaadd, cmd_qadel, cmd_qalist
from ._cmd_status import cmd_ping, cmd_status
from ._cmd_update import cmd_update
from ._cmd_wiki import cmd_wiki

# CommandHandler в PTB не обрабатывает channel_post — маршрутизируем вручную (см. lifecycle.py).
_CHANNEL_COMMAND_HANDLERS: dict[str, object] = {}


def _register_channel_commands() -> None:
    if _CHANNEL_COMMAND_HANDLERS:
        return

    _CHANNEL_COMMAND_HANDLERS.update(
        {
            "help": cmd_help,
            "id": cmd_id,
            "admincheck": cmd_admincheck,
            "wiki": cmd_wiki,
            "ping": cmd_ping,
            "status": cmd_status,
            "error": cmd_error,
            "fix": cmd_fix,
            "qaadd": cmd_qaadd,
            "qalist": cmd_qalist,
            "qadel": cmd_qadel,
            "update": cmd_update,
        }
    )


async def on_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команды в Telegram-канале (паблик): апдейты приходят как channel_post, не message."""
    _register_channel_commands()

    msg = update.effective_message

    if not msg or not msg.text:
        return

    head = (msg.text.split(maxsplit=1)[0] if msg.text else "").strip()

    if not head.startswith("/"):
        return

    cmd = head.split("@", 1)[0][1:].lower()
    handler = _CHANNEL_COMMAND_HANDLERS.get(cmd)

    if handler is None:
        return

    await handler(update, context)  # type: ignore[misc]
