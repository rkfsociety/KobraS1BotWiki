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
        "err_header": "Ошибка {code}",
        "err_cause": "Причина: {text}",
        "err_fix": "Что делать: {text}",
        "match": "совпадение: {score}%",
        "already_in_wiki": "Похоже, это уже описано в вики:",
        "cmd_id": "ID этого чата:",
        "cmd_type": "Тип",
        "wiki_usage": "Использование: /wiki <вопрос или ключевые слова>",
        "wiki_nothing_found": "Ничего не нашёл в вики.",
        "wiki_low_conf": "Нашёл что-то похожее, но уверенность низкая. Попробуй уточнить запрос.",
        "ping": "OK. Я на связи.",
        "bot_status": "Статус бота:",
        "error_usage": "Использование: ответь на сообщение бота командой /error",
        "fix_usage_reply": "Использование: ответь на сообщение бота командой /fix <ссылка>",
        "fix_usage": "Использование: /fix <ссылка>",
        "unknown_reply_ctx": "Не понимаю, к какому запросу относится тот ответ. Попробуй повторить вопрос.",
        "error_no_better": "Понял. Попробовал поискать ещё раз — лучше не нашёл. Похоже, ответа нет.",
        "error_retry": "Попробовал ещё раз, вот что нашёл:",
        "fix_confirm": "Ок, вот правильная ссылка:",
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
        "err_header": "Error {code}",
        "err_cause": "Cause: {text}",
        "err_fix": "What to do: {text}",
        "match": "match: {score}%",
        "already_in_wiki": "This seems to be already covered in the wiki:",
        "cmd_id": "Chat ID:",
        "cmd_type": "Type",
        "wiki_usage": "Usage: /wiki <question or keywords>",
        "wiki_nothing_found": "I couldn’t find anything in the wiki.",
        "wiki_low_conf": "I found something similar, but confidence is low. Try refining your query.",
        "ping": "OK. I’m online.",
        "bot_status": "Bot status:",
        "error_usage": "Usage: reply to the bot message with /error",
        "fix_usage_reply": "Usage: reply to the bot message with /fix <link>",
        "fix_usage": "Usage: /fix <link>",
        "unknown_reply_ctx": "I can’t tell which query that reply belongs to. Please ask again.",
        "error_no_better": "Got it. I tried searching again, but couldn’t find a better result. Looks like there’s no answer.",
        "error_retry": "I tried again. Here’s what I found:",
        "fix_confirm": "OK, here is the correct link:",
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
