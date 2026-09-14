"""Проверки командного меню Telegram."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from telegram import BotCommandScopeAllChatAdministrators, BotCommandScopeDefault

from app.bot.command_menu import configure_command_menu


def test_command_menu_publishes_localized_public_and_admin_scopes():
    bot = type("Bot", (), {"set_my_commands": AsyncMock()})()

    asyncio.run(configure_command_menu(bot))

    calls = bot.set_my_commands.await_args_list
    assert len(calls) == 11

    ru_public = calls[0].args[0]
    ru_admin = calls[2].args[0]
    en_public = calls[4].args[0]
    en_admin = calls[6].args[0]

    assert [command.command for command in ru_public] == ["start", "help"]
    assert [command.command for command in en_public] == ["start", "help"]
    assert "wiki" not in [command.command for command in ru_public]
    assert "wiki" in [command.command for command in ru_admin]
    assert "mute" in [command.command for command in ru_admin]
    assert ru_admin[0].description == "Запустить бота"
    assert en_admin[0].description == "Start the bot"
    assert calls[0].kwargs["language_code"] == "ru"
    assert calls[4].kwargs["language_code"] == "en"
    assert isinstance(calls[0].kwargs["scope"], BotCommandScopeDefault)
    assert isinstance(calls[3].kwargs["scope"], BotCommandScopeAllChatAdministrators)


def test_command_menu_fallback_has_no_language_code():
    bot = type("Bot", (), {"set_my_commands": AsyncMock()})()

    asyncio.run(configure_command_menu(bot))

    for call in bot.set_my_commands.await_args_list[-3:]:
        assert "language_code" not in call.kwargs
