"""Язык ответа и строки UI."""
from __future__ import annotations

import re

from telegram.ext import ContextTypes

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")


def _detect_user_lang(*, text: str, user_lang_code: str | None) -> str:
    """
    Возвращает "ru" или "en" для языка ответа.
    Приоритет:
    - если в сообщении есть кириллица => ru
    - иначе по language_code Telegram (ru/uk/be/kk/... считаем русскоязычными)
    - иначе en
    """
    t = (text or "").strip()
    if _CYRILLIC_RE.search(t):
        return "ru"
    lc = (user_lang_code or "").strip().lower()
    if lc.startswith(("ru", "uk", "be", "kk", "ky", "uz", "tg", "hy", "ka")):
        return "ru"
    return "en"


def _t(lang: str, key: str) -> str:
    ru = {
        "generic_help": (
            "Могу помочь, но нужно чуть больше данных.\n"
            "Напиши, пожалуйста: модель принтера (например Kobra S1/Kobra 3) и что именно случилось "
            "(ошибка с кодом, что не работает, что хотите сделать)."
        ),
        "no_guide_for_model": (
            "Извини, в вики не нашёл отдельной статьи по этому вопросу именно для твоей модели. "
            "Похоже, такого гайда там ещё нет или он под другим названием — честно, подсказать ссылкой не могу."
        ),
        "found_in_wiki": "Нашёл в вики:",
        "thanks_found_in_wiki": "Спасибо за уточнение, нашёл в вики:",
        "still_uncertain": "Спасибо! Всё ещё не могу уверенно найти статью. Попробуй добавить модель и/или код ошибки.",
        "error_code_clarify": (
            "По коду <b>{code}</b> есть разные статьи для разных моделей ({variants}).\n"
            "Уточни, пожалуйста, <b>модель принтера</b> (например: <b>Kobra S1</b> / <b>Kobra 3</b> / <b>Kobra 3 Max</b>).\n"
            "Ответь на это сообщение."
        ),
        "clarify_prompt": (
            "Похоже, ответ есть в вики, но мне не хватает данных.\n"
            "Уточни, пожалуйста, <b>модель принтера</b> {hint} (например: <b>Kobra S1</b>) и/или <b>код ошибки</b>.\n"
            "Ответь на это сообщение."
        ),
        "clarify_prompt_no_error_code": (
            "Похоже, ответ есть в вики, но мне не хватает данных.\n"
            "Уточни, пожалуйста, <b>модель принтера</b> {hint} (например: <b>Kobra S1</b>).\n"
            "Ответь на это сообщение."
        ),
        "err_header": "Ошибка {code}",
        "err_cause": "Причина: {text}",
        "err_fix": "Что делать: {text}",
        "match": "совпадение: {score}%",
        "already_in_wiki": "Похоже, это уже описано в вики:",
        "cmd_id": "ID этого чата:",
        "cmd_type": "Тип",
        "cmd_topic_id": "ID темы (topic_id, для ALLOWED_TOPIC_IDS)",
        "wiki_usage": "Использование: /wiki <вопрос или ключевые слова>",
        "wiki_nothing_found": "Ничего не нашёл в вики.",
        "wiki_low_conf": "Нашёл что-то похожее, но уверенность низкая. Попробуй уточнить запрос.",
        "ping": "OK. Я на связи.",
        "ping_commit_running": "Коммит (текущий HEAD)",
        "ping_commit_upstream": "Коммит на {remote}/{branch} (после git fetch)",
        "ping_git_fail": "Git: {detail}",
        "ping_update_suggest": "На удалённой ветке другой коммит — обновите бота командой /update (админ).",
        "ping_git_ok": "Рабочая копия совпадает с {remote}/{branch}.",
        "bot_status": "Статус бота:",
        "error_usage": "Использование: ответь на сообщение бота командой /error",
        "fix_usage_reply": "Использование: ответь на сообщение бота командой /fix <ссылка>",
        "fix_usage": "Использование: /fix <ссылка>",
        "unknown_reply_ctx": "Не понимаю, к какому запросу относится тот ответ. Попробуй повторить вопрос.",
        "error_no_better": "Понял. Попробовал поискать ещё раз — лучше не нашёл. Похоже, ответа нет.",
        "error_retry": "Попробовал ещё раз, вот что нашёл:",
        "fix_confirm": "Ок, вот правильная ссылка:",
        "manual_qa_header": "<b>Ответ (добавлен вручную)</b>",
        "qaadd_usage": (
            "Использование: одно сообщение (данные пишутся в <code>data/manual_qa.json</code> в репозитории).\n"
            "<code>/qaadd</code> <i>вопрос или несколько через |||</i>\n"
            "<code>---</code>\n"
            "<i>текст ответа (несколько строк можно)</i>\n\n"
            "Несколько формулировок: "
            "<code>как снять сопло|||замена сопла</code> до разделителя <code>---</code>.\n"
            "После сохранения при включённом <code>MANUAL_QA_GIT_PUSH</code> бот сделает "
            "<code>git commit</code> и <code>git push</code> (нужен доступ к origin)."
        ),
        "qalist_empty": "Ручных ответов пока нет.",
        "qalist_header": "<b>Ручные ответы</b> (номер — для <code>/qadel</code>):",
        "qadel_usage": "Использование: <code>/qadel</code> <i>номер строки из /qalist</i>",
        "qaadd_ok": "Запись добавлена ({detail}).",
        "qaadd_fail": "Не удалось: {reason}",
        "qadel_ok": "Запись {n} удалена.",
        "qadel_fail": "Не удалось: {reason}",
        "update_uptodate": "Код уже совпадает с GitHub, перезапуск не нужен.",
        "update_fail": "Не удалось обновить с GitHub: {reason}",
        "update_ok": "Обновлено: {detail}. Перезапускаю бота…",
        "word_yes": "да",
        "word_no": "нет",
        "admincheck_header": "Проверка прав для служебных команд",
        "admincheck_private": "Чат: личка с ботом — доступ к служебным командам открыт (как при настройке).",
        "admincheck_channel": "Чат: Telegram-канал (паблик) — служебные команды для админов канала.",
        "admincheck_chat": "Чат: id {chat_id}, тип: {chat_type}",
        "admincheck_telegram": "Роль в Telegram (get_chat_member): {status}",
        "admincheck_member_fail": "Не удалось запросить роль у Telegram: {reason}",
        "admincheck_user": "Вы: id {user_id}{username}",
        "admincheck_developer": "В списке разработчиков бота: {yesno}",
        "admincheck_bot_access": "Бот считает, что служебные команды вам доступны: {yesno}",
        "admincheck_footer": "Если вы видите этот ответ — бот уже распознал у вас доступ к этой команде в этом чате.",
    }
    en = {
        "generic_help": (
            "I can help, but I need a bit more info.\n"
            "Please send: your printer model (e.g. Kobra S1 / Kobra 3) and what exactly happened "
            "(an error code, what is not working, what you’re trying to do)."
        ),
        "no_guide_for_model": (
            "Sorry, I couldn’t find a dedicated wiki article for your exact printer model. "
            "It looks like the guide doesn’t exist yet or it’s under a different name — I can’t link a reliable page."
        ),
        "found_in_wiki": "Found in the wiki:",
        "thanks_found_in_wiki": "Thanks! Found in the wiki:",
        "still_uncertain": "Thanks! I still can’t confidently find the right article. Try adding your model and/or an error code.",
        "error_code_clarify": (
            "For code <b>{code}</b> there are different articles for different models ({variants}).\n"
            "Please specify your <b>printer model</b> (e.g. <b>Kobra S1</b> / <b>Kobra 3</b> / <b>Kobra 3 Max</b>).\n"
            "Reply to this message."
        ),
        "clarify_prompt": (
            "It looks like the answer is in the wiki, but I’m missing some details.\n"
            "Please specify your <b>printer model</b> {hint} (e.g. <b>Kobra S1</b>) and/or the <b>error code</b>.\n"
            "Reply to this message."
        ),
        "clarify_prompt_no_error_code": (
            "It looks like the answer is in the wiki, but I’m missing some details.\n"
            "Please specify your <b>printer model</b> {hint} (e.g. <b>Kobra S1</b>).\n"
            "Reply to this message."
        ),
        "err_header": "Error {code}",
        "err_cause": "Cause: {text}",
        "err_fix": "What to do: {text}",
        "match": "match: {score}%",
        "already_in_wiki": "This seems to be already covered in the wiki:",
        "cmd_id": "Chat ID:",
        "cmd_type": "Type",
        "cmd_topic_id": "Topic id (thread_id, for ALLOWED_TOPIC_IDS)",
        "wiki_usage": "Usage: /wiki <question or keywords>",
        "wiki_nothing_found": "I couldn’t find anything in the wiki.",
        "wiki_low_conf": "I found something similar, but confidence is low. Try refining your query.",
        "ping": "OK. I’m online.",
        "ping_commit_running": "Current commit (HEAD)",
        "ping_commit_upstream": "Commit on {remote}/{branch} (after git fetch)",
        "ping_git_fail": "Git: {detail}",
        "ping_update_suggest": "Remote branch has a different commit — run /update (admin) to refresh the bot.",
        "ping_git_ok": "Working tree matches {remote}/{branch}.",
        "bot_status": "Bot status:",
        "error_usage": "Usage: reply to the bot message with /error",
        "fix_usage_reply": "Usage: reply to the bot message with /fix <link>",
        "fix_usage": "Usage: /fix <link>",
        "unknown_reply_ctx": "I can’t tell which query that reply belongs to. Please ask again.",
        "error_no_better": "Got it. I tried searching again, but couldn’t find a better result. Looks like there’s no answer.",
        "error_retry": "I tried again. Here’s what I found:",
        "fix_confirm": "OK, here is the correct link:",
        "manual_qa_header": "<b>Manual answer</b>",
        "qaadd_usage": (
            "Usage: one message (stored in <code>data/manual_qa.json</code> in the repo).\n"
            "<code>/qaadd</code> <i>question (use ||| between several triggers)</i>\n"
            "<code>---</code>\n"
            "<i>answer text (multiple lines OK)</i>\n\n"
            "If <code>MANUAL_QA_GIT_PUSH</code> is enabled, the bot runs <code>git commit</code> and <code>git push</code>."
        ),
        "qalist_empty": "No manual answers yet.",
        "qalist_header": "<b>Manual answers</b> (number for <code>/qadel</code>):",
        "qadel_usage": "Usage: <code>/qadel</code> <i>line number from /qalist</i>",
        "qaadd_ok": "Entry added ({detail}).",
        "qaadd_fail": "Failed: {reason}",
        "qadel_ok": "Entry {n} removed.",
        "qadel_fail": "Failed: {reason}",
        "update_uptodate": "Already up to date with GitHub. No restart.",
        "update_fail": "Could not update from GitHub: {reason}",
        "update_ok": "Updated: {detail}. Restarting the bot…",
        "word_yes": "yes",
        "word_no": "no",
        "admincheck_header": "Admin command access check",
        "admincheck_private": "Chat: private with the bot — maintenance commands are allowed (for setup/testing).",
        "admincheck_channel": "Chat: Telegram channel — maintenance commands for channel admins.",
        "admincheck_chat": "Chat: id {chat_id}, type: {chat_type}",
        "admincheck_telegram": "Telegram role (get_chat_member): {status}",
        "admincheck_member_fail": "Could not fetch role from Telegram: {reason}",
        "admincheck_user": "You: id {user_id}{username}",
        "admincheck_developer": "In the bot developer list: {yesno}",
        "admincheck_bot_access": "Bot considers maintenance commands allowed for you: {yesno}",
        "admincheck_footer": "If you see this reply, the bot already treated you as allowed to run this command in this chat.",
    }
    table = ru if lang == "ru" else en
    return table.get(key, key)


def _lang_from_message(*, context: ContextTypes.DEFAULT_TYPE, msg, text: str) -> str:
    user_lang_code = (
        msg.from_user.language_code
        if (msg and msg.from_user and getattr(msg.from_user, "language_code", None))
        else None
    )
    lang = _detect_user_lang(text=text, user_lang_code=user_lang_code)
    context.application.bot_data["last_user_lang"] = lang
    return lang
