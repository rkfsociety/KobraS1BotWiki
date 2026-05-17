"""Тексты команды /help (plain text — без HTML, чтобы Telegram не отклонял разметку)."""
from __future__ import annotations


def _mention(bot_username: str) -> str:
    u = (bot_username or "").strip().lstrip("@")
    return f"@{u}" if u else "@…"


def format_help_message(*, lang: str, is_admin: bool, bot_username: str) -> str:
    m = _mention(bot_username)

    if lang == "ru":
        if is_admin:
            return (
                "Справка (вы администратор чата)\n\n"
                "Служебные команды\n"
                "• /help — эта справка\n"
                "• /id — ID чата и тип (для ALLOWED_CHAT_IDS / ALLOWED_TOPIC_IDS в .env)\n"
                "• /admincheck — роль в Telegram (get_chat_member) и как бот трактует доступ к служебным командам\n"
                "• /wiki — ручной поиск по вики (запрос через пробел после команды)\n"
                "• /ping — бот на связи, краткая сводка\n"
                "• /status — статус индекса, лимиты и проверка доступа чата/темы\n"
                "• /error — ответьте reply на сообщение бота: ссылка была неверной, перепоиск\n"
                "• /fix — reply на сообщение бота и правильный URL в той же команде\n"
                "• /qaadd — ручная пара «вопрос → ответ» (без аргументов — подсказка по формату)\n"
                "• /qalist — список ручных ответов\n"
                "• /qadel — удалить запись по номеру из /qalist\n"
                "• /update — подтянуть код с GitHub и перезапустить бота (как GIT_AUTOPULL)\n\n"
                "Обычные участники в своём /help видят только, как задавать вопросы; "
                "служебные команды им недоступны (бот не отвечает). "
                "На вопросы в группе бот отвечает сам; @ можно для уточнений или если фраза не похожа на вопрос."
            )
        return (
            "Справка\n\n"
            "Вы можете получать ссылки на статьи вики, если задаёте вопрос в группе — "
            "бот сам распознаёт вопрос (?, «как», «не работает» и т.п.). "
            f"Упоминание {m} не обязательно; оно нужно для уточнений или если фраза не похожа на вопрос.\n\n"
            "Команды поиска и диагностики (/wiki, /id, /status и др.) доступны только "
            "администраторам чата; без прав бот не отвечает.\n\n"
            "• /help — эта справка"
        )

    if is_admin:
        return (
            "Help (you are a chat administrator)\n\n"
            "Admin commands\n"
            "• /help — this help\n"
            "• /id — chat ID and type (for ALLOWED_CHAT_IDS / ALLOWED_TOPIC_IDS in .env)\n"
            "• /admincheck — Telegram role (get_chat_member) and how the bot treats maintenance access\n"
            "• /wiki — manual wiki search (type your query after the command)\n"
            "• /ping — quick health check\n"
            "• /status — index status, limits, chat/topic access check\n"
            "• /error — reply to the bot message: wrong link, re-search\n"
            "• /fix — reply to the bot message and include the correct URL in the command\n"
            "• /qaadd — manual Q&A pair (send without args for usage)\n"
            "• /qalist — list manual answers\n"
            "• /qadel — delete an entry by its number from /qalist\n"
            "• /update — pull latest code from GitHub and restart the bot (same as GIT_AUTOPULL)\n\n"
            "Regular members only see how to ask questions in their /help; "
            "maintenance commands are ignored (no reply). "
            "The bot answers questions in the group without @; mention the bot for follow-ups or non-question text."
        )
    return (
        "Help\n\n"
        "You can get wiki links by asking a question in the group — the bot detects questions "
        f"automatically. Mentioning {m} is optional; use it for follow-ups or non-question messages.\n\n"
        "Search and diagnostic commands (/wiki, /id, /status, etc.) work only for chat "
        "administrators; without rights the bot does not respond.\n\n"
        "• /help — this help"
    )
