"""Тексты команды /help (HTML) для админов чата и обычных участников."""
from __future__ import annotations

import html


def format_help_message(*, lang: str, is_admin: bool, bot_username: str) -> str:
    u = html.escape((bot_username or "").strip().lstrip("@"), quote=True)
    if not u:
        u = "…"

    if lang == "ru":
        if is_admin:
            return (
                "<b>Справка (вы администратор чата)</b>\n\n"
                "<b>Служебные команды</b>\n"
                "• <code>/help</code> — эта справка\n"
                "• <code>/id</code> — ID чата и тип (для <code>ALLOWED_CHAT_IDS</code> / "
                "<code>ALLOWED_TOPIC_IDS</code> в .env)\n"
                "• <code>/wiki</code> — ручной поиск по вики (напишите запрос через пробел после команды)\n"
                "• <code>/ping</code> — бот на связи, краткая сводка\n"
                "• <code>/status</code> — статус индекса, лимиты и проверка доступа чата/темы\n"
                "• <code>/error</code> — ответьте <b>reply</b> на сообщение бота: ссылка была неверной, перепоиск\n"
                "• <code>/fix</code> — ответьте <b>reply</b> на сообщение бота и укажите правильный URL в той же команде\n"
                "• <code>/qaadd</code> — ручная пара «вопрос → ответ» (см. <code>/help</code> или подсказку без аргументов)\n"
                "• <code>/qalist</code> — список ручных ответов\n"
                "• <code>/qadel</code> — удалить запись по номеру из <code>/qalist</code>\n"
                "• <code>/update</code> — подтянуть код с GitHub и перезапустить бота (как <code>GIT_AUTOPULL</code>)\n\n"
                "<b>Обычные участники</b> в своём <code>/help</code> видят только, как задавать вопросы; "
                "если они введут служебную команду, бот <b>не ответит</b> (команды только для админов чата). "
                "Обычно вопрос задают, упоминая бота: "
                "<code>@" + u + "</code>."
            )
        return (
            "<b>Справка</b>\n\n"
            "Вы можете получать ссылки на статьи вики, если <b>задаёте вопрос в группе</b> "
            "и при этом <b>упоминаете бота</b> <code>@" + u + "</code> "
            "(или отвечаете боту там, где это разрешено настройками группы).\n\n"
            "Команды поиска и диагностики (<code>/wiki</code>, <code>/id</code>, <code>/status</code> и другие) "
            "доступны только <b>администраторам чата</b>; при вводе без прав бот <b>не отвечает</b>.\n\n"
            "• <code>/help</code> — эта справка"
        )

    if is_admin:
        return (
            "<b>Help (you are a chat administrator)</b>\n\n"
            "<b>Admin commands</b>\n"
            "• <code>/help</code> — this help\n"
            "• <code>/id</code> — chat ID and type (for <code>ALLOWED_CHAT_IDS</code> / "
            "<code>ALLOWED_TOPIC_IDS</code> in .env)\n"
            "• <code>/wiki</code> — manual wiki search (type your query after the command)\n"
            "• <code>/ping</code> — quick health check\n"
            "• <code>/status</code> — index status, limits, chat/topic access check\n"
            "• <code>/error</code> — <b>reply</b> to the bot message: wrong link, re-search\n"
            "• <code>/fix</code> — <b>reply</b> to the bot message and include the correct URL in the command\n"
            "• <code>/qaadd</code> — manual Q&amp;A pair (see <code>/help</code> or send the command without args for usage)\n"
            "• <code>/qalist</code> — list manual answers\n"
            "• <code>/qadel</code> — delete an entry by its number from <code>/qalist</code>\n"
            "• <code>/update</code> — pull latest code from GitHub and restart the bot (same as <code>GIT_AUTOPULL</code>)\n\n"
            "<b>Regular members</b> only see how to ask questions in their <code>/help</code>; "
            "if they try a maintenance command, the bot <b>will not reply</b> (commands are for chat admins only). "
            "Usually you mention the bot: "
            "<code>@" + u + "</code>."
        )
    return (
        "<b>Help</b>\n\n"
        "You can get wiki links by <b>asking a question in the group</b> and <b>mentioning the bot</b> "
        "<code>@" + u + "</code> (or replying to the bot where your group settings allow it).\n\n"
        "Search and diagnostic commands (<code>/wiki</code>, <code>/id</code>, <code>/status</code>, etc.) "
        "work only for <b>chat administrators</b>; without rights the bot <b>does not respond</b>.\n\n"
        "• <code>/help</code> — this help"
    )
