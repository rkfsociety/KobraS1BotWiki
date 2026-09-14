"""Командное меню Telegram с отдельными списками для админов и участников."""
from __future__ import annotations

from telegram import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
)


_PUBLIC_COMMANDS = {
    "ru": (
        ("start", "Запустить бота"),
        ("help", "Справка по боту"),
    ),
    "en": (
        ("start", "Start the bot"),
        ("help", "Bot help"),
    ),
}

_ADMIN_COMMANDS = {
    "ru": (
        ("id", "Показать ID чата и темы"),
        ("admincheck", "Проверить роль и доступ"),
        ("app", "Открыть приложение поддержки"),
        ("wiki", "Найти статью в вики"),
        ("ii", "Ответить ИИ на сообщение пользователя"),
        ("ping", "Проверить, что бот на связи"),
        ("status", "Показать статус бота и индекса"),
        ("stats", "Показать статистику группы"),
        ("error", "Перепоиск ссылки в ответе"),
        ("fix", "Исправить ссылку в ответе"),
        ("qaadd", "Добавить ручной ответ"),
        ("qalist", "Показать ручные ответы"),
        ("qadel", "Удалить ручной ответ"),
        ("update", "Обновить код и перезапустить бота"),
        ("ban", "Заблокировать пользователя"),
        ("unban", "Разблокировать пользователя"),
        ("kick", "Удалить пользователя из группы"),
        ("mute", "Выдать пользователю мут"),
        ("unmute", "Снять мут с пользователя"),
        ("warn", "Выдать предупреждение"),
        ("unwarn", "Снять предупреждение"),
        ("warnings", "Показать предупреждения"),
        ("clearwarns", "Очистить предупреждения"),
        ("del", "Удалить сообщение"),
        ("pin", "Закрепить сообщение"),
        ("unpin", "Открепить сообщение"),
    ),
    "en": (
        ("id", "Show chat and topic IDs"),
        ("admincheck", "Check role and access"),
        ("app", "Open the support app"),
        ("wiki", "Search the wiki"),
        ("ii", "Ask AI to answer a user message"),
        ("ping", "Check that the bot is online"),
        ("status", "Show bot and index status"),
        ("stats", "Show group statistics"),
        ("error", "Search the answer link again"),
        ("fix", "Fix a link in the answer"),
        ("qaadd", "Add a manual answer"),
        ("qalist", "List manual answers"),
        ("qadel", "Delete a manual answer"),
        ("update", "Update code and restart the bot"),
        ("ban", "Ban a user"),
        ("unban", "Unban a user"),
        ("kick", "Remove a user from the group"),
        ("mute", "Mute a user"),
        ("unmute", "Unmute a user"),
        ("warn", "Issue a warning"),
        ("unwarn", "Remove a warning"),
        ("warnings", "Show warnings"),
        ("clearwarns", "Clear warnings"),
        ("del", "Delete a message"),
        ("pin", "Pin a message"),
        ("unpin", "Unpin a message"),
    ),
}


def _make_commands(items: tuple[tuple[str, str], ...]) -> list[BotCommand]:
    return [BotCommand(command=command, description=description) for command, description in items]


async def configure_command_menu(bot) -> None:
    """Публикует команды Telegram в нужных областях и на нужных языках."""
    for language_code in ("ru", "en"):
        public = _make_commands(_PUBLIC_COMMANDS[language_code])
        admin = _make_commands((*_PUBLIC_COMMANDS[language_code], *_ADMIN_COMMANDS[language_code]))

        await bot.set_my_commands(
            public,
            scope=BotCommandScopeDefault(),
            language_code=language_code,
        )
        await bot.set_my_commands(
            public,
            scope=BotCommandScopeAllGroupChats(),
            language_code=language_code,
        )
        await bot.set_my_commands(
            admin,
            scope=BotCommandScopeAllPrivateChats(),
            language_code=language_code,
        )
        await bot.set_my_commands(
            admin,
            scope=BotCommandScopeAllChatAdministrators(),
            language_code=language_code,
        )

    # Русский список — безопасный fallback для пользователей без ru/en.
    public_ru = _make_commands(_PUBLIC_COMMANDS["ru"])
    admin_ru = _make_commands((*_PUBLIC_COMMANDS["ru"], *_ADMIN_COMMANDS["ru"]))
    await bot.set_my_commands(public_ru, scope=BotCommandScopeDefault())
    await bot.set_my_commands(admin_ru, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(admin_ru, scope=BotCommandScopeAllChatAdministrators())
