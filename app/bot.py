from __future__ import annotations

import html
import logging
import os
import re
import time
from collections import deque
import asyncio
from pathlib import Path
from logging.handlers import RotatingFileHandler
import json

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.constants import ChatType, MessageEntityType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, TypeHandler, filters

from app.config import load_settings
from app.printer_catalog import explain_door_vs_design
from app.error_codes_catalog import ErrorCodeInfo, ensure_error_codes_catalog, merge_manual_overrides
from app.web_wiki_index import WebWikiDoc, WebWikiIndex, WebWikiIndexer
from app.ru_layer import expand_queries
from app.translate_ru import Translator


_COOLDOWN_EXEMPT_USERS: frozenset[int] = frozenset(
    {
        # Ручной allowlist: для этого пользователя не применяем COOLDOWN_SECONDS.
        5111236617,
    }
)


_CLARIFY_STORE = Path(".cache/clarify_pending.json")
_ANSWER_CTX_STORE = Path(".cache/answer_context.json")
_FEEDBACK_STORE = Path(".cache/feedback.json")
_FIX_STORE = Path(".cache/fixes.json")


def _clarify_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _load_clarify_store() -> dict[str, dict]:
    try:
        if not _CLARIFY_STORE.exists():
            return {}
        raw = json.loads(_CLARIFY_STORE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_clarify_store(data: dict[str, dict]) -> None:
    _CLARIFY_STORE.parent.mkdir(parents=True, exist_ok=True)
    _CLARIFY_STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


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


def _load_answer_ctx_store() -> dict[str, dict]:
    try:
        if not _ANSWER_CTX_STORE.exists():
            return {}
        raw = json.loads(_ANSWER_CTX_STORE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_answer_ctx_store(data: dict[str, dict]) -> None:
    _ANSWER_CTX_STORE.parent.mkdir(parents=True, exist_ok=True)
    _ANSWER_CTX_STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _answer_ctx_key(chat_id: int, bot_message_id: int) -> str:
    return f"{chat_id}:{bot_message_id}"


def _record_bot_answer_context(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    bot_message_id: int,
    query: str,
    url: str | None,
) -> None:
    """
    Запоминаем, на какой запрос бот ответил данным сообщением.
    Нужно для команды /error (перепоиск и "обучение").
    """
    store = context.application.bot_data.setdefault("answer_ctx_store", {})
    if not isinstance(store, dict):
        store = {}
        context.application.bot_data["answer_ctx_store"] = store

    store[_answer_ctx_key(chat_id, bot_message_id)] = {
        "q": query,
        "url": url,
        "ts": time.time(),
    }
    # Ограничим размер, чтобы не разрасталось бесконечно
    if len(store) > 800:
        # удаляем самые старые
        items = sorted(store.items(), key=lambda kv: float(kv[1].get("ts", 0.0)))
        for k, _ in items[:200]:
            store.pop(k, None)
    _save_answer_ctx_store(store)


def _load_feedback_store() -> dict[str, list[str]]:
    """
    query_norm -> [bad_url, ...]
    """
    try:
        if not _FEEDBACK_STORE.exists():
            return {}
        raw = json.loads(_FEEDBACK_STORE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, list):
                out[k] = [str(x) for x in v if isinstance(x, str)]
        return out
    except Exception:
        return {}


def _save_feedback_store(data: dict[str, list[str]]) -> None:
    _FEEDBACK_STORE.parent.mkdir(parents=True, exist_ok=True)
    _FEEDBACK_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _remember_bad_answer(*, context: ContextTypes.DEFAULT_TYPE, query: str, bad_url: str | None) -> None:
    if not bad_url:
        return
    qn = _norm_text(query)
    fb = context.application.bot_data.setdefault("feedback_store", {})
    if not isinstance(fb, dict):
        fb = {}
        context.application.bot_data["feedback_store"] = fb
    lst = fb.get(qn)
    if not isinstance(lst, list):
        lst = []
    if bad_url not in lst:
        lst.append(bad_url)
    # ограничим на запрос
    fb[qn] = lst[-20:]
    _save_feedback_store(fb)


def _excluded_urls_for_query(*, context: ContextTypes.DEFAULT_TYPE, query: str) -> set[str]:
    fb = context.application.bot_data.get("feedback_store", {})
    if not isinstance(fb, dict):
        return set()
    lst = fb.get(_norm_text(query), [])
    if not isinstance(lst, list):
        return set()
    return {str(x) for x in lst if isinstance(x, str)}


def _load_fix_store() -> dict[str, str]:
    """
    query_norm -> good_url
    """
    try:
        if not _FIX_STORE.exists():
            return {}
        raw = json.loads(_FIX_STORE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, str] = {}
        for k, v in raw.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                out[k] = v.strip()
        return out
    except Exception:
        return {}


def _save_fix_store(data: dict[str, str]) -> None:
    _FIX_STORE.parent.mkdir(parents=True, exist_ok=True)
    _FIX_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _remember_good_fix(*, context: ContextTypes.DEFAULT_TYPE, query: str, good_url: str) -> None:
    qn = _norm_text(query)
    fixes = context.application.bot_data.setdefault("fix_store", {})
    if not isinstance(fixes, dict):
        fixes = {}
        context.application.bot_data["fix_store"] = fixes
    fixes[qn] = good_url
    # ограничим размер
    if len(fixes) > 800:
        # не знаем ts, поэтому просто обрежем по ключам
        for k in sorted(fixes.keys())[:200]:
            fixes.pop(k, None)
    _save_fix_store(fixes)


def _preferred_fix_url(*, context: ContextTypes.DEFAULT_TYPE, query: str) -> str | None:
    fixes = context.application.bot_data.get("fix_store", {})
    if not isinstance(fixes, dict):
        return None
    return fixes.get(_norm_text(query))


def _search_best_with_model_bias_excluding(
    index: WebWikiIndex,
    variants: list[str],
    *,
    context_text: str,
    topic_for_keywords: str | None,
    exclude_urls: set[str],
    top_k: int = 28,
) -> tuple[WebWikiDoc | None, int]:
    # Если есть "правильная" ссылка, заданная через /fix — используем её.
    preferred = _preferred_fix_url(context=context, query=context_text)
    if preferred:
        for d in getattr(index, "_docs", []):  # type: ignore[attr-defined]
            if getattr(d, "url", None) == preferred:
                return d, 100
    doc, score = _search_best_with_model_bias(
        index,
        variants,
        context_text=context_text,
        topic_for_keywords=topic_for_keywords,
        top_k=top_k,
    )
    if not doc:
        return None, score
    if doc.url in exclude_urls:
        # попробуем найти следующий — делаем "ручной" проход без exclude
        hints = _model_slug_hints(context_text)
        by_url: dict[str, tuple[WebWikiDoc, int]] = {}
        for q in variants:
            q = (q or "").strip()
            if not q:
                continue
            for d2, sc in index.search(q, top_k=top_k):
                if d2.url in exclude_urls:
                    continue
                bonus = _url_model_bonus(d2.url, hints)
                penalty = _url_model_penalty(d2.url, hints, topic_for_keywords)
                kw = _topic_path_bonus(topic_for_keywords, d2.url)
                part_pen = _wrong_part_for_topic_penalty(topic_for_keywords, d2.url)
                adj_raw = int(sc) + bonus - penalty + kw - part_pen
                prev = by_url.get(d2.url)
                if prev is None or adj_raw > prev[1]:
                    by_url[d2.url] = (d2, adj_raw)
        if not by_url:
            return None, -1
        best_doc2, raw_best = max(by_url.values(), key=lambda x: x[1])
        capped = max(0, min(100, raw_best))
        return best_doc2, capped
    return doc, score


def _log_bot_reply(kind: str, chat_id: int, user_id: int | None = None, **extra: object) -> None:
    """Явная отметка в логе: бот что-то отправил в чат (удобно искать по `bot_reply`)."""
    parts: list[str] = [f"bot_reply kind={kind}", f"chat={chat_id}"]
    if user_id is not None:
        parts.append(f"user={user_id}")
    for key, val in extra.items():
        if val is None:
            continue
        parts.append(f"{key}={val}")
    logging.info(" ".join(parts))


def _load_manual_error_codes() -> dict[str, ErrorCodeInfo]:
    try:
        path = Path("wiki/error-codes-manual.json")
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, ErrorCodeInfo] = {}
        for k, v in raw.items():
            if not isinstance(v, dict):
                continue
            code = str(v.get("code") or k).strip()
            if not code.isdigit():
                continue
            out[code] = ErrorCodeInfo(
                code=code,
                title=str(v.get("title") or "").strip(),
                cause=str(v.get("cause") or "").strip(),
                fix=str(v.get("fix") or "").strip(),
            )
        return out
    except Exception:
        return {}


def _format_error_code_info(info: ErrorCodeInfo, *, lang: str) -> str:
    def tr(s: str) -> str:
        s2 = (s or "").strip()
        if not s2:
            return ""
        if lang != "ru":
            return s2
        # Точечные переводы для часто встречающихся ошибок ACE Pro.
        # Если строка не распознана — оставляем EN, но с русскими подписью/контекстом ниже.
        mapping = {
            "The number of filaments in the ACE Pro does not meet the requirements of the model": "Количество филамента в ACE Pro не соответствует требованиям модели",
            "The number of filaments placed in the ACE Pro is too small to perform color mapping of the multi-color model.": "В ACE Pro установлено слишком мало филамента, чтобы выполнить цветовое сопоставление для многоцветной модели.",
            "ACE Pro is working and cannot be upgraded": "ACE Pro занят и не может быть обновлён",
            "ACE Pro is performing other tasks.": "ACE Pro выполняет другие задачи.",
            "The firmware of ACE Pro needs to be upgraded after the tasks are completed.": "Обновите прошивку ACE Pro после завершения текущих задач.",
        }
        return mapping.get(s2, s2)

    code = html.escape(info.code)
    title = tr(info.title)
    cause = tr(info.cause)
    fix = tr(info.fix)

    parts: list[str] = [f"<b>{html.escape(_t(lang, 'err_header').format(code=code))}</b>"]
    if title:
        parts.append(f"<b>{html.escape(title)}</b>")
    if cause:
        parts.append(html.escape(_t(lang, "err_cause").format(text=cause)))
    if fix:
        parts.append(html.escape(_t(lang, "err_fix").format(text=fix)))
    return "\n".join(parts).strip()


async def _format_error_code_info_ru(*, context: ContextTypes.DEFAULT_TYPE, info: ErrorCodeInfo) -> str:
    """
    Переводим title/cause/fix на русский (лениво) и кэшируем.
    Делается только для ответа из каталога, чтобы не блочить основной поиск/индексацию.
    """
    tr = context.application.bot_data.get("ru_translator")
    if not isinstance(tr, Translator):
        tr = Translator(cache_path=Path(".cache/ru_translations.json"))
        context.application.bot_data["ru_translator"] = tr

    # Язык выбираем по последнему сообщению пользователя (проставляем в on_message).
    lang = context.application.bot_data.get("last_user_lang") or "ru"
    if lang != "ru":
        return _format_error_code_info(info, lang="en")

    title = await tr.translate_en_ru(info.title)
    cause = await tr.translate_en_ru(info.cause)
    fix = await tr.translate_en_ru(info.fix)
    return _format_error_code_info(ErrorCodeInfo(code=info.code, title=title, cause=cause, fix=fix), lang="ru")


def _sync_clarify_pending_from_disk(pending: dict[tuple[int, int], dict]) -> None:
    """
    Подмешиваем состояние с диска в in-memory pending.
    Нужно, если ответ на уточнение обработал другой процесс (два polling на один токен)
    или память устарела относительно .cache/clarify_pending.json.
    """
    store = _load_clarify_store()
    for k, v in store.items():
        if not isinstance(v, dict):
            continue
        try:
            chat_s, user_s = str(k).split(":", 1)
            tup = (int(chat_s), int(user_s))
        except Exception:
            continue
        old = pending.get(tup)
        ts_new = float(v.get("ts") or 0.0)
        if old is None or ts_new >= float(old.get("ts") or 0.0):
            pending[tup] = v


_PRINTER_MENTION_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"kobra|photon|vyper|chiron|predator|anycubic|megax|mega[\s-]?x|mega[\s-]?pro|mega[\s-]?s|"
    r"wash[\s-]?(and|&)?[\s-]?cure|mono[\s-]?m|m5s|"
    r"кобра|фотон|вайпер|аникубик"
    r")(?![a-z0-9])"
)


def _printer_mentioned(text: str) -> bool:
    """В тексте явно названа линейка/семейство принтера (латиница или кириллица)."""
    if _PRINTER_MENTION_RE.search(text):
        return True
    tl = text.lower()
    # номера серий часто пишут отдельно: "s1", "k2", "m5" и т.п. — только с контекстом принтера
    if re.search(r"\bkobra\b", tl) and re.search(r"\b(s1|s2|go|max|neo|plus|combo|pro)\b", tl):
        return True
    if re.search(r"\bphoton\b", tl) and re.search(r"\b(m3|m5|mono|ultra|x6)\b", tl):
        return True
    return False


def _topic_needs_printer_model(text: str) -> bool:
    """Тема вопроса обычно специфична для модели (без модели ответ легко промахнется)."""
    t = text.lower()
    ru = (
        "экструдер",
        "сопло",
        "хотэнд",
        "прошив",
        # "ошибка" слишком общее слово (напр. "ошибка природы") — модель по нему не уточняем.
        # Коды ошибок обрабатываются отдельно через _extract_error_code/_is_error_code_query.
        "калибр",
        "левел",
        "не печатает",
        "ремень",
        "застрял",
        "заклинил",
        "стол",
        "подогрев",
        "сопл",
        "двер",
        "петл",
        "стекл",
    )
    en = (
        "extruder",
        "nozzle",
        "hotend",
        "hot end",
        "firmware",
        "calibrat",
        "leveling",
        "level ",
        " bed",
        "heated bed",
        "build plate",
        "belt",
        "jam",
        "clog",
        "stepper",
        "door",
        "glass door",
        "hinge",
        "enclosure",
    )
    return any(x in t for x in ru + en)


def _extract_error_code(text: str) -> str | None:
    """
    Возвращает числовой код ошибки (4–7 цифр), если он явно присутствует в тексте.
    Формат на вики обычно: /error-codes/<code>-code/...
    """
    m = re.search(r"\b(\d{4,7})\b", text.lower())
    return m.group(1) if m else None


def _is_error_code_query(text: str) -> bool:
    """
    Сообщение, где ключевой смысл — код ошибки (например "ошибка 11407").
    """
    code = _extract_error_code(text)
    if not code:
        return False
    t = text.lower()
    # если рядом есть явная "ошибка/err/error" — точно запрос по коду
    return any(k in t for k in ("ошибк", "error", "err"))


def _error_code_variant_suffix(code: str, url: str) -> str | None:
    """
    /en/error-codes/<code>-code/<suffix> -> suffix
    /en/error-codes/<code>-code -> None
    """
    u = (url or "").lower().rstrip("/")
    base = f"/error-codes/{code}-code"
    if base not in u:
        return None
    after = u.split(base, 1)[1]
    if not after:
        return None
    after = after.lstrip("/")
    if not after:
        return None
    return after.split("/", 1)[0] or None


def _error_code_target_suffix(text: str) -> str | None:
    """
    Пытаемся понять, для какой линейки нужна страница кода ошибки.
    Поддерживаем явные сокращения (s1/k3/k3m) и названия моделей (через hints).
    """
    tl = text.lower()
    # явные сокращения
    if re.search(r"\bk3m\b", tl):
        return "k3m"
    if re.search(r"\bk3\b", tl) or re.search(r"\bkobra\s*3\b", tl) or "kobra-3" in tl:
        return "k3"
    if re.search(r"\bs1\b", tl) or "kobra-s1" in tl or re.search(r"kobra\s*s\s*1\b", tl):
        return "s1"

    hints = _model_slug_hints(text)
    if "kobra-s1" in hints or "kobra-s1-combo" in hints:
        return "s1"
    if "kobra-3" in hints or "kobra-3-combo" in hints:
        return "k3"
    if "kobra-max" in hints or "kobra-max-combo" in hints:
        return "k3m"
    return None


def _error_code_candidates(index: WebWikiIndex, code: str) -> list[WebWikiDoc]:
    target = f"/error-codes/{code}-code"
    out: list[WebWikiDoc] = []
    for d in getattr(index, "_docs", []):  # type: ignore[attr-defined]
        try:
            u = (d.url or "").lower()
        except Exception:
            continue
        if target in u:
            out.append(d)
    return out


def _pick_error_code_doc(index: WebWikiIndex, code: str, *, context_text: str) -> WebWikiDoc | None:
    """
    Для кодов ошибок не используем fuzzy-поиск (он может путать коды).
    Ищем только страницы вида /error-codes/<code>-code...
    """
    candidates = _error_code_candidates(index, code)
    if not candidates:
        return None
    # Если вариантов несколько — пытаемся выбрать по модели из текста.
    target_suffix = _error_code_target_suffix(context_text)
    if target_suffix:
        for d in candidates:
            if _error_code_variant_suffix(code, d.url) == target_suffix:
                return d
    # Предпочитаем базовую страницу кода без суффиксов (/s1, /k3, и т.п.)
    base = f"https://wiki.anycubic.com/en/error-codes/{code}-code"
    for d in candidates:
        if d.url.rstrip("/") == base:
            return d
    # Если суффикса не нашли и базовой нет — неоднозначно, пусть вызывающий уточнит модель.
    return candidates[0] if len(candidates) == 1 else None

def _needs_model_clarification(text: str) -> bool:
    # Для кодов ошибок модель не спрашиваем — либо найдём страницу по коду, либо промолчим.
    if _is_error_code_query(text):
        return False
    return _topic_needs_printer_model(text) and not _printer_mentioned(text)


def _is_generic_help_without_context(text: str) -> bool:
    """
    "помогите/спасите" без конкретики — лучше попросить уточнение, а не искать по вики наугад.
    """
    t = (text or "").lower()
    if not any(k in t for k in ("помогите", "спасите", "help", "памагити", "спаситипамагити")):
        return False
    # если есть код ошибки или модель/принтер или тех. тема — это уже конкретика
    if _is_error_code_query(text) or _printer_mentioned(text) or _topic_needs_printer_model(text):
        return False
    return True


def _model_slug_hints(text: str) -> frozenset[str]:
    """Подстроки пути вики (латиница), по которым отличают линейки принтеров."""
    out: set[str] = set()
    tl = text.lower()
    combo = "combo" in tl or "комбо" in tl
    # Kobra 3 Max — до ветки «Kobra 3», иначе спутать с обычной тройкой
    is_kobra_3_max = bool(re.search(r"kobra\s*3\s*max\b", tl) or "kobra-3-max" in tl)
    if is_kobra_3_max:
        if combo:
            out.add("kobra-max-combo")
            out.add("kobra-max")
        else:
            out.add("kobra-max")
    elif re.search(r"kobra\s*max\b", tl) or "kobra-max" in tl:
        if combo:
            out.add("kobra-max-combo")
            out.add("kobra-max")
        else:
            out.add("kobra-max")

    if re.search(r"kobra\s*s\s*1\b", tl) or re.search(r"kobra\s*s1\b", tl) or "kobra-s1" in tl:
        if combo or "kobra-s1-combo" in tl:
            out.add("kobra-s1-combo")
            out.add("kobra-s1")  # тот же корпус; путь вики часто с суффиксом -combo
        else:
            out.add("kobra-s1")
    if (re.search(r"kobra\s*3\b", tl) or "kobra-3" in tl or re.search(r"кобра\s*3\b", tl)) and not is_kobra_3_max:
        if combo or "kobra-3-combo" in tl:
            out.add("kobra-3-combo")
            out.add("kobra-3")
        else:
            out.add("kobra-3")
    if re.search(r"kobra\s*2\b", tl) or "kobra-2" in tl or re.search(r"кобра\s*2\b", tl):
        out.add("kobra-2")
    if re.search(r"kobra\s*go\b", tl) or "kobra-go" in tl:
        out.add("kobra-go")
    if re.search(r"kobra\s*neo\b", tl) or "kobra-neo" in tl:
        out.add("kobra-neo")
    if re.search(r"\bvyper\b", tl):
        out.add("vyper")
    if re.search(r"\bchiron\b", tl):
        out.add("chiron")
    if re.search(r"\bphoton\b", tl):
        out.add("photon")
    return frozenset(out)


def _url_model_bonus(url: str, hints: frozenset[str]) -> int:
    if not hints:
        return 0
    u = url.lower()
    hits = sum(1 for h in hints if h in u)
    return min(78, hits * 40)


def _topic_path_bonus(topic: str | None, url: str) -> int:
    """Слегка подталкиваем URL под формулировку исходного вопроса (только уточнение по модели)."""
    if not topic:
        return 0
    tl = topic.lower()
    u = url.lower()
    b = 0
    # Коды ошибок: предпочитаем раздел /error-codes/ и не уходим в FAQ.
    if re.search(r"\b1\d{4}\b", tl):
        if "/error-codes/" in u:
            b += 70
        if "/faq" in u or u.rstrip("/").endswith("/faq"):
            b -= 55
    if "экструдер" in tl or "extruder" in tl:
        if "extruder" in u:
            b += 24
        if "print-head" in u and "extruder" not in u:
            b -= 20
    if "сопло" in tl or "nozzle" in tl:
        if "nozzle" in u:
            b += 20
    if "хотэнд" in tl or "hotend" in tl or "hot end" in tl:
        if "hotend" in u or "hot-end" in u:
            b += 20
    if "двер" in tl or "door" in tl or "петл" in tl or "hinge" in tl:
        if "glass-door" in u:
            b += 52
        elif "door" in u and "glass" in u:
            b += 28
    return b


def _topic_is_door_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    return any(k in tl for k in ("двер", "door", "петл", "hinge", "enclosure", "glass door"))


def _topic_is_nozzle_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    return any(k in tl for k in ("сопло", "nozzle"))


def _topic_is_nozzle_silicone_intent(topic: str | None) -> bool:
    if not topic:
        return False
    tl = topic.lower()
    return any(
        k in tl
        for k in (
            "силикон",
            "втулк",
            "носок",
            "чехол",
            "silicone",
            "sock",
        )
    )


def _nozzle_guide_url_plausible(url: str, *, allow_silicone: bool) -> bool:
    """
    Если спросили «как поменять сопло», не нужно отдавать гайды про silicone sock/sleeve.
    """
    u = url.lower().replace("_", "-")
    if "nozzle" not in u:
        return False
    # если это явно про силиконовую втулку/носок — только когда пользователь просил именно это
    if ("silicone" in u or "sock" in u) and not allow_silicone:
        return False
    # стараемся требовать "replacement/replace" для "поменять/заменить"
    if any(k in u for k in ("replacement", "replace")):
        return True
    # иногда страницы названы странно, но всё равно про сопло — пропускаем, если хоть явно nozzle и guide
    if "guide" in u:
        return True
    return True


def _wrong_part_for_topic_penalty(topic: str | None, url: str) -> int:
    """Тема «дверь», а URL про другое узло — сильный штраф (иначе тянет purge-wiper из-за replace)."""
    if not _topic_is_door_intent(topic):
        return 0
    u = url.lower().replace("_", "-")
    if "glass-door" in u or ("glass" in u and "door" in u):
        return 0
    bad = (
        "wiper",
        "purge",
        "filament",
        "extruder",
        "nozzle",
        "hotend",
        "motor",
        "belt",
        "power-supply",
        "psu",
        "heated-bed",
        "heatbed",
        "bed-replacement",
        "firmware",
        "thermistor",
        "print-head",
    )
    for b in bad:
        if b in u:
            return 78
    return 0


def _guide_url_matches_model_hints(url: str, hints: frozenset[str]) -> bool:
    """Если пользователь назвал модель — в ссылке должен быть тот же slug (иначе гайда «для неё» нет)."""
    # Для кодов ошибок модель часто кодируется иначе (/s1, /kobra-3 и т.п.),
    # поэтому жёсткое совпадение slug ломает выдачу. Разрешаем /error-codes/ всегда.
    if "/error-codes/" in url.lower():
        return True
    if not hints:
        return True
    u = url.lower()
    return any(h in u for h in hints)


def _door_guide_url_plausible(url: str) -> bool:
    u = url.lower().replace("_", "-")
    if "glass-door" in u:
        return True
    if "door" in u and ("glass" in u or "hinge" in u or "cover" in u):
        return True
    return False


def _response_wiki_url_acceptable(question: str, url: str) -> bool:
    """Не слать ссылку, если модель в URL не та или тема (например дверь) явно не совпадает со slug статьи."""
    # Для запросов по коду ошибки отдаём только точные страницы /error-codes/<code>-code...
    code = _extract_error_code(question)
    if code and _is_error_code_query(question):
        u = url.lower()
        if "/error-codes/" not in u:
            return False
        # Не отдаём общий раздел /error-codes — только страницу конкретного кода.
        if f"/{code}-code" not in u:
            return False
    else:
        # Если это НЕ запрос по коду ошибки — не отдаём раздел /error-codes вообще,
        # иначе фразы типа "ошибка природы, помогите" тянут туда.
        if "/error-codes" in url.lower():
            return False
    if not _guide_url_matches_model_hints(url, _model_slug_hints(question)):
        return False
    if _topic_is_door_intent(question) and not _door_guide_url_plausible(url):
        return False
    if _topic_is_nozzle_intent(question) and not _nozzle_guide_url_plausible(
        url, allow_silicone=_topic_is_nozzle_silicone_intent(question)
    ):
        return False
    return True


def _no_guide_for_model_message() -> str:
    # legacy helper; prefer _t(lang, "no_guide_for_model")
    return _t("ru", "no_guide_for_model")


async def _maybe_reply_printer_design_vs_question(
    msg,
    *,
    question: str,
    chat_id: int,
    settings,
    user_id: int | None,
) -> bool:
    """Справочник конструкции: например дверь камеры на открытой Kobra 3 — объясняем без вики."""
    hints_d = _model_slug_hints(question)
    expl = explain_door_vs_design(question, hints_d)
    if not expl:
        return False
    await msg.reply_text(expl, disable_web_page_preview=True)
    if settings.log_decisions:
        logging.info(
            "bot_reply kind=printer_design_fact chat=%s hints=%s",
            chat_id,
            " ".join(sorted(hints_d)),
        )
    _log_bot_reply("printer_design_fact", chat_id, user_id, hints=" ".join(sorted(hints_d)))
    return True


async def _try_send_error_code_clarify(
    *,
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    code: str,
    candidates: list[WebWikiDoc],
    settings,
) -> bool:
    """
    Если по коду ошибки есть несколько страниц (разные модели) — просим уточнить модель.
    """
    if not settings.clarify_enabled or not msg.from_user:
        return False
    # собираем список вариантов по суффиксам URL
    suffixes: list[str] = []
    for d in candidates:
        s = _error_code_variant_suffix(code, d.url)
        if s:
            suffixes.append(s)
    uniq = sorted(set(suffixes))
    if len(uniq) < 2:
        return False

    pretty = ", ".join(uniq).upper()
    lang = context.application.bot_data.get("last_user_lang") or "ru"
    sent = await msg.reply_text(
        _t(lang, "error_code_clarify").format(code=html.escape(code), variants=html.escape(pretty)),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    pending = context.application.bot_data.setdefault("clarify_pending", {})
    ckey = (chat_id, msg.from_user.id)
    now2 = time.time()
    pending[ckey] = {"original": text, "ts": now2, "prompt_message_id": sent.message_id}
    store = _load_clarify_store()
    store[_clarify_key(chat_id, msg.from_user.id)] = pending[ckey]
    _save_clarify_store(store)
    _log_bot_reply("error_code_clarify_prompt", chat_id, msg.from_user.id, message_id=sent.message_id, code=code, variants=pretty)
    return True


async def _reply_no_guide_for_model(
    msg,
    *,
    chat_id: int,
    settings,
    user_id: int | None,
    best_url: str,
    hints: frozenset[str],
) -> None:
    lang = context.application.bot_data.get("last_user_lang") or "ru"
    await msg.reply_text(_t(lang, "no_guide_for_model"), disable_web_page_preview=True)
    if settings.log_decisions:
        logging.info(
            "skip chat=%s reason=no_guide_for_model url=%s hints=%s",
            chat_id,
            best_url,
            " ".join(sorted(hints)),
        )
    _log_bot_reply(
        "no_matching_guide",
        chat_id,
        user_id,
        url=best_url,
        hints=" ".join(sorted(hints)),
    )


def _arm_clarify_correction_window(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    original: str,
    settings,
) -> None:
    """После ответа на уточнение — даём несколько reply-поправок модели."""
    if not settings.clarify_enabled or settings.clarify_correction_max <= 0:
        return
    key = (chat_id, user_id)
    cd = context.application.bot_data.setdefault("clarify_correction_cooldown_until", {})
    if time.time() < float(cd.get(key, 0.0)):
        return
    st = context.application.bot_data.setdefault("clarify_correction_state", {})
    st[key] = {
        "original": original.strip(),
        "remaining": settings.clarify_correction_max,
        "ts": time.time(),
        # Разрешаем продолжать цепочку только reply на последний ответ бота.
        "expected_reply_to_mid": None,
    }


def _is_reply_to_bot(update: Update, *, bot_id: int | None) -> tuple[bool, int | None]:
    """
    Возвращает (is_reply_to_bot, reply_message_id).
    reply_message_id — message_id того сообщения, на которое отвечают.
    """
    msg = update.effective_message
    if not msg or not msg.reply_to_message or not msg.reply_to_message.from_user:
        return False, None
    if bot_id is None:
        return False, msg.reply_to_message.message_id
    return msg.reply_to_message.from_user.id == bot_id, msg.reply_to_message.message_id


def _reply_is_expected_by_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    В группах игнорируем любые reply, если бот сам их не просил.
    Разрешаем только:
    - reply на уточняющий prompt (clarify_pending.prompt_message_id)
    - reply на последний ответ бота в рамках окна поправок (clarify_correction_state.expected_reply_to_mid)
    """
    msg = update.effective_message
    if not msg or not update.effective_chat or not msg.from_user:
        return False
    bot_id = context.application.bot_data.get("bot_id")
    is_reply_to_bot, reply_mid = _is_reply_to_bot(update, bot_id=bot_id)
    if not is_reply_to_bot or reply_mid is None:
        return False

    key = (update.effective_chat.id, msg.from_user.id)

    pending = context.application.bot_data.setdefault("clarify_pending", {})
    _sync_clarify_pending_from_disk(pending)
    item = pending.get(key)
    if item:
        expected_mid = item.get("prompt_message_id")
        if expected_mid is not None and int(expected_mid) == int(reply_mid):
            return True

    st = context.application.bot_data.setdefault("clarify_correction_state", {})
    corr = st.get(key)
    if corr:
        exp = corr.get("expected_reply_to_mid")
        if exp is not None and int(exp) == int(reply_mid):
            return True

    return False


async def _deliver_clarify_combined(
    msg,
    *,
    context: ContextTypes.DEFAULT_TYPE,
    combined: str,
    original: str,
    chat_id: int,
    from_user: int,
    settings,
    trace: str,
) -> str:
    """
    Общая логика после уточнения модели: справочник конструкции и поиск вики.
    trace: 'followup' | 'correction'
    Возвращает: printer_design | wiki | uncertain | no_guide
    """
    # Защита: для кодов ошибок не уточняем и не отвечаем "общими" страницами.
    # Либо находим точную страницу /error-codes/<code>-code..., либо молчим.
    if _is_error_code_query(original) or _is_error_code_query(combined):
        lang = context.application.bot_data.get("last_user_lang") or "ru"
        index: WebWikiIndex = context.application.bot_data["wiki_index"]
        code = _extract_error_code(combined) or _extract_error_code(original)
        best_doc = _pick_error_code_doc(index, code, context_text=combined) if code else None
        best_score = 100 if best_doc else -1
        if not best_doc:
            if settings.log_decisions:
                logging.info(
                    "skip chat=%s reason=error_code_not_found trace=%s score=%d",
                    chat_id,
                    trace,
                    best_score,
                )
            return "silent"
        url = best_doc.url
        title = html.escape(best_doc.title)
        reply = (
            _t(lang, "found_in_wiki") + "\n"
            f"• <b>{title}</b>\n"
            f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
            f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>"
        )
        sent = await msg.reply_text(reply, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
        # Подстрахуемся: даже если кто-то ответит reply, мы не хотим продолжать цепочку по кодам ошибок.
        _log_bot_reply(
            "error_code_wiki",
            chat_id,
            from_user,
            score=best_score,
            url=url,
        )
        return "wiki"

    if await _maybe_reply_printer_design_vs_question(
        msg,
        question=combined,
        chat_id=chat_id,
        settings=settings,
        user_id=from_user,
    ):
        if settings.log_decisions and trace == "correction":
            logging.info(
                "clarify_correction chat=%s user=%s outcome=printer_design",
                chat_id,
                from_user,
            )
        return "printer_design"

    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    variants = expand_queries(combined) if settings.ru_layer_enabled else [combined]
    best_doc, best_score = _search_best_with_model_bias(
        index, variants, context_text=combined, topic_for_keywords=original
    )

    uncertain_kind = "clarify_correction_uncertain" if trace == "correction" else "clarify_followup_uncertain"
    wiki_kind = "clarify_correction_wiki" if trace == "correction" else "clarify_followup_wiki"

    if not best_doc or best_score < settings.min_score:
        sent = await msg.reply_text(
            _t(context.application.bot_data.get("last_user_lang") or "ru", "still_uncertain"),
            disable_web_page_preview=True,
        )
        _log_bot_reply(
            uncertain_kind,
            chat_id,
            from_user,
            score=best_score if best_doc else None,
            url=(best_doc.url if best_doc else None),
        )
        # Разрешаем следующий reply только на этот ответ бота
        st = context.application.bot_data.setdefault("clarify_correction_state", {})
        if (chat_id, from_user) in st:
            st[(chat_id, from_user)]["expected_reply_to_mid"] = sent.message_id
        return "uncertain"

    if not _response_wiki_url_acceptable(combined, best_doc.url):
        await _reply_no_guide_for_model(
            msg,
            chat_id=chat_id,
            settings=settings,
            user_id=from_user,
            best_url=best_doc.url,
            hints=_model_slug_hints(combined),
        )
        return "no_guide"

    url = best_doc.url
    title = html.escape(best_doc.title)
    lang = context.application.bot_data.get("last_user_lang") or "ru"
    reply = (
        _t(lang, "thanks_found_in_wiki") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>"
    )
    sent = await msg.reply_text(reply, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
    hints = _model_slug_hints(combined)
    _log_bot_reply(
        wiki_kind,
        chat_id,
        from_user,
        score=best_score,
        url=url,
        hints=" ".join(sorted(hints)) if hints else "-",
    )
    # Разрешаем следующий reply только на этот ответ бота
    st = context.application.bot_data.setdefault("clarify_correction_state", {})
    if (chat_id, from_user) in st:
        st[(chat_id, from_user)]["expected_reply_to_mid"] = sent.message_id
    return "wiki"


def _url_model_penalty(url: str, hints: frozenset[str], topic: str | None = None) -> int:
    """Если модель в запросе ясна, но URL явно про другую линейку — сильный штраф."""
    u = url.lower()
    if not hints:
        return 0
    if any(h in u for h in hints):
        return 0
    pen = 0
    siblings: dict[str, tuple[str, ...]] = {
        "kobra-3": ("kobra-s1", "kobra-2", "vyper", "chiron"),
        "kobra-3-combo": ("kobra-s1", "kobra-2", "vyper", "chiron"),
        "kobra-s1": ("kobra-3", "kobra-2", "vyper", "chiron"),
        "kobra-s1-combo": ("kobra-3", "kobra-2", "vyper", "chiron"),
        "kobra-2": ("kobra-s1", "kobra-3", "vyper", "chiron"),
        "kobra-max": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "kobra-max-combo": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "kobra-go": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "kobra-neo": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
        "vyper": ("kobra-s1", "kobra-3", "kobra-2"),
        "chiron": ("kobra-s1", "kobra-3", "kobra-2", "vyper"),
    }
    for h in hints:
        for bad in siblings.get(h, ()):
            if bad in u:
                pen = max(pen, 65)
    return pen


def _search_best_with_model_bias(
    index: WebWikiIndex,
    variants: list[str],
    *,
    context_text: str,
    topic_for_keywords: str | None = None,
    top_k: int = 28,
) -> tuple[WebWikiDoc | None, int]:
    """
    Поиск по вариантам запроса с учётом явной модели в context_text (бонус/штраф по URL).
    Итоговый score для порогов — в диапазоне 0..100, но победитель выбирается по «сырым» баллам до cap.
    """
    hints = _model_slug_hints(context_text)
    by_url: dict[str, tuple[WebWikiDoc, int]] = {}
    for q in variants:
        q = (q or "").strip()
        if not q:
            continue
        for doc, score in index.search(q, top_k=top_k):
            bonus = _url_model_bonus(doc.url, hints)
            penalty = _url_model_penalty(doc.url, hints, topic_for_keywords)
            kw = _topic_path_bonus(topic_for_keywords, doc.url)
            part_pen = _wrong_part_for_topic_penalty(topic_for_keywords, doc.url)
            adj_raw = int(score) + bonus - penalty + kw - part_pen
            prev = by_url.get(doc.url)
            if prev is None or adj_raw > prev[1]:
                by_url[doc.url] = (doc, adj_raw)
    if not by_url:
        return None, -1
    best_doc, raw_best = max(by_url.values(), key=lambda x: x[1])
    capped = max(0, min(100, raw_best))
    return best_doc, capped


def _clarify_model_hint_html(text: str) -> str:
    """
    Примеры моделей в тексте уточнения: экструдер/стол и т.д. — только FDM;
    смола/LCD — только фотополимерные; иначе оба класса отдельно (без смешивания там, где нелогично).
    """
    t = text.lower()
    fdm_kw = (
        "экструдер",
        "сопло",
        "хотэнд",
        "ремень",
        "стол",
        "подогрев",
        "сопл",
        "застрял",
        "заклинил",
        "extruder",
        "nozzle",
        "hotend",
        "hot end",
        "belt",
        "heated bed",
        "build plate",
        "jam",
        "clog",
        "stepper",
        "двер",
        "петл",
        "door",
        "hinge",
        "enclosure",
    )
    resin_kw = (
        "смол",
        "резин",
        "фотополимер",
        "ванн",
        "vat",
        "экспоз",
        "resin",
        "exposure",
        "peel",
        "fep",
    )
    is_fdm = any(k in t for k in fdm_kw)
    is_resin = any(k in t for k in resin_kw)
    if is_fdm and not is_resin:
        return "(например: <b>Kobra S1 / Kobra 3 / Vyper</b>)"
    if is_resin and not is_fdm:
        return "(например: <b>Photon Mono M5s / Photon M3 / Photon Ultra</b>)"
    return "(FDM: <b>Kobra / Vyper</b>; смола: <b>Photon / Mono</b>)"


async def _try_send_printer_clarify(
    *,
    msg,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    best_doc,
    best_score: int,
    settings,
    require_score_floor: bool,
    score_floor: int,
) -> str | None:
    """
    Если нужна модель и она не указана — отправляем уточнение (или блокируем ответ).
    Returns:
      None — уточнение не требуется, можно отвечать ссылкой
      "sent" — отправили запрос уточнения
      "blocked" — нужна модель, но cooldown; ссылку не шлём
    """
    if not settings.clarify_enabled or not msg.from_user:
        return None
    if not _needs_model_clarification(text):
        return None
    if require_score_floor and best_score < score_floor:
        return None

    cooldown = context.application.bot_data.setdefault("clarify_last_ts", {})
    ckey = (chat_id, msg.from_user.id)
    last = float(cooldown.get(ckey, 0.0))
    now2 = time.time()
    if now2 - last < settings.clarify_cooldown_seconds:
        if settings.log_decisions:
            logging.info(
                "skip chat=%s reason=need_printer_model_cooldown score=%d url=%s",
                chat_id,
                best_score,
                best_doc.url,
            )
        return "blocked"

    cc_state = context.application.bot_data.setdefault("clarify_correction_state", {})
    cc_state.pop(ckey, None)
    cd = context.application.bot_data.setdefault("clarify_correction_cooldown_until", {})
    cd.pop(ckey, None)

    pending = context.application.bot_data.setdefault("clarify_pending", {})
    cooldown[ckey] = now2
    hint = _clarify_model_hint_html(text)
    lang = context.application.bot_data.get("last_user_lang") or "ru"
    sent = await msg.reply_text(
        _t(lang, "clarify_prompt").format(hint=hint),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    pending[ckey] = {"original": text, "ts": now2, "prompt_message_id": sent.message_id}
    store = _load_clarify_store()
    store[_clarify_key(chat_id, msg.from_user.id)] = pending[ckey]
    _save_clarify_store(store)
    if settings.log_decisions:
        logging.info("clarify chat=%s score=%d url=%s reason=model_required", chat_id, best_score, best_doc.url)
    _log_bot_reply(
        "clarify_prompt",
        chat_id,
        msg.from_user.id,
        message_id=sent.message_id,
        score=best_score,
        url=best_doc.url,
    )
    return "sent"


async def _maybe_handle_clarification_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Если пользователь ответил reply на уточняющий вопрос бота — пробуем повторный поиск.
    Возвращает True, если сообщение обработано.
    """
    msg = update.effective_message
    if not msg or not msg.text or not update.effective_chat:
        return False

    settings = context.application.bot_data["settings"]
    pending = context.application.bot_data.setdefault("clarify_pending", {})
    _sync_clarify_pending_from_disk(pending)
    from_user = msg.from_user.id if msg.from_user else 0
    key = (update.effective_chat.id, from_user)
    item = pending.get(key)
    if not item:
        if settings.log_decisions and msg.reply_to_message and msg.reply_to_message.from_user:
            logging.info(
                "clarify_followup_no_pending chat=%s user=%s reply_from=%s reply_mid=%s",
                update.effective_chat.id,
                from_user,
                msg.reply_to_message.from_user.id,
                msg.reply_to_message.message_id,
            )
        return False

    # Уточнение принимаем только как reply на сообщение бота
    bot_id = context.application.bot_data.get("bot_id")
    is_reply_to_bot = False
    reply_from_id = None
    reply_msg_id = None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        reply_from_id = msg.reply_to_message.from_user.id
        reply_msg_id = msg.reply_to_message.message_id
    if bot_id and reply_from_id is not None:
        is_reply_to_bot = reply_from_id == bot_id

    if not is_reply_to_bot:
        if settings.log_decisions:
            logging.info(
                "clarify_followup_ignored chat=%s user=%s bot_id=%s reply_from_id=%s has_reply=%s",
                update.effective_chat.id,
                from_user,
                bot_id,
                reply_from_id,
                str(bool(msg.reply_to_message)).lower(),
            )
        return False

    expected_mid = item.get("prompt_message_id")
    if expected_mid is not None and reply_msg_id is not None and int(expected_mid) != int(reply_msg_id):
        if settings.log_decisions:
            logging.info(
                "clarify_followup_ignored chat=%s user=%s reason=reply_to_other_message expected_mid=%s got_mid=%s",
                update.effective_chat.id,
                from_user,
                expected_mid,
                reply_msg_id,
            )
        return False

    original = str(item.get("original") or "").strip()
    if not original:
        pending.pop(key, None)
        return False

    combined = f"{original} {msg.text.strip()}"

    pending.pop(key, None)
    store = _load_clarify_store()
    store.pop(_clarify_key(update.effective_chat.id, from_user), None)
    _save_clarify_store(store)

    await _deliver_clarify_combined(
        msg,
        context=context,
        combined=combined,
        original=original,
        chat_id=update.effective_chat.id,
        from_user=from_user,
        settings=settings,
        trace="followup",
    )
    _arm_clarify_correction_window(
        context,
        update.effective_chat.id,
        from_user,
        original,
        settings,
    )
    return True


async def _maybe_handle_clarify_correction_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Reply на любое сообщение бота после цепочки clarify: пользователь поправил модель (1–N раз), затем кулдаун.
    """
    msg = update.effective_message
    if not msg or not msg.text or not update.effective_chat or not msg.from_user:
        return False

    settings = context.application.bot_data["settings"]
    if not settings.clarify_enabled or settings.clarify_correction_max <= 0:
        return False

    chat_id = update.effective_chat.id
    from_user = msg.from_user.id
    key = (chat_id, from_user)

    bot_id = context.application.bot_data.get("bot_id")
    reply_from_id = None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        reply_from_id = msg.reply_to_message.from_user.id
    if not bot_id or reply_from_id is None or reply_from_id != bot_id:
        return False

    st = context.application.bot_data.setdefault("clarify_correction_state", {})
    item = st.get(key)
    if not item:
        return False

    now = time.time()

    if now - float(item.get("ts", 0.0)) > settings.clarify_correction_ttl_seconds:
        st.pop(key, None)
        if settings.log_decisions:
            logging.info(
                "clarify_correction_expired chat=%s user=%s",
                chat_id,
                from_user,
            )
        return False

    original = str(item.get("original") or "").strip()
    if not original:
        st.pop(key, None)
        return False

    expected_mid = item.get("expected_reply_to_mid")
    if expected_mid is not None:
        # принимаем поправку только reply на последний ответ бота в цепочке
        _, reply_mid = _is_reply_to_bot(update, bot_id=bot_id)
        if reply_mid is None or int(reply_mid) != int(expected_mid):
            return False

    combined = f"{original} {msg.text.strip()}"
    await _deliver_clarify_combined(
        msg,
        context=context,
        combined=combined,
        original=original,
        chat_id=chat_id,
        from_user=from_user,
        settings=settings,
        trace="correction",
    )

    item["ts"] = now
    rem = int(item.get("remaining", 0)) - 1
    if rem <= 0:
        st.pop(key, None)
        cd = context.application.bot_data.setdefault("clarify_correction_cooldown_until", {})
        cd[key] = now + float(settings.clarify_cooldown_seconds)
        if settings.log_decisions:
            logging.info(
                "clarify_correction_exhausted chat=%s user=%s cooldown_s=%s",
                chat_id,
                from_user,
                settings.clarify_cooldown_seconds,
            )
    else:
        item["remaining"] = rem
        st[key] = item

    return True


def _is_triggered_message(update: Update, *, bot_username: str | None, bot_id: int | None) -> bool:
    msg = update.effective_message
    if not msg:
        return False

    # В личке можно отвечать всегда
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        return True

    # Упоминание @username
    if bot_username and msg.entities:
        uname = bot_username.lower().lstrip("@")
        for ent in msg.entities:
            if ent.type == MessageEntityType.MENTION:
                part = (msg.text or "")[ent.offset : ent.offset + ent.length]
                if part.lower().lstrip("@") == uname:
                    return True

    return False


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_message:
        return
    chat = update.effective_chat
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    text = (
        _t(lang, "cmd_id") + "\n"
        f"<code>{chat.id}</code>\n"
        f"{html.escape(_t(lang, 'cmd_type'))}: <code>{html.escape(chat.type)}</code>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    uid = msg.from_user.id if msg.from_user else None
    _log_bot_reply("cmd_id", update.effective_chat.id, uid)


async def cmd_wiki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    query = " ".join(context.args or []).strip()
    uid = msg.from_user.id if msg.from_user else None
    chat_id = update.effective_chat.id
    if not query:
        await msg.reply_text(_t(lang, "wiki_usage"), disable_web_page_preview=True)
        _log_bot_reply("cmd_wiki_usage", chat_id, uid)
        return

    if await _maybe_reply_printer_design_vs_question(
        msg,
        question=query,
        chat_id=chat_id,
        settings=settings,
        user_id=uid,
    ):
        return

    variants = expand_queries(query) if settings.ru_layer_enabled else [query]
    best_doc, best_score = _search_best_with_model_bias(
        index, variants, context_text=query, topic_for_keywords=query
    )

    if not best_doc:
        await msg.reply_text(_t(lang, "wiki_nothing_found"), disable_web_page_preview=True)
        _log_bot_reply("cmd_wiki_not_found", chat_id, uid, query=query[:80])
        return

    if best_score < settings.min_score:
        await msg.reply_text(_t(lang, "wiki_low_conf"), disable_web_page_preview=True)
        _log_bot_reply("cmd_wiki_low_score", chat_id, uid, score=best_score, min_score=settings.min_score, url=best_doc.url)
        return

    clarify_cmd = await _try_send_printer_clarify(
        msg=msg,
        context=context,
        chat_id=chat_id,
        text=query,
        best_doc=best_doc,
        best_score=best_score,
        settings=settings,
        require_score_floor=False,
        score_floor=0,
    )
    if clarify_cmd in ("sent", "blocked"):
        return

    url = best_doc.url
    if not _response_wiki_url_acceptable(query, url):
        await _reply_no_guide_for_model(
            msg,
            chat_id=chat_id,
            settings=settings,
            user_id=uid,
            best_url=url,
            hints=_model_slug_hints(query),
        )
        return

    title = html.escape(best_doc.title)
    reply = (
        _t(lang, "found_in_wiki") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>"
    )
    await msg.reply_text(reply, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
    _log_bot_reply("cmd_wiki", chat_id, uid, score=best_score, url=url)


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    text = (
        _t(lang, "ping") + "\n"
        f"chat_id: <code>{update.effective_chat.id}</code>\n"
        f"wiki_docs: <code>{index.doc_count}</code>\n"
        f"QUESTIONS_ONLY: <code>{settings.questions_only}</code>\n"
        f"REQUIRE_TRIGGER: <code>{settings.require_trigger}</code>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    uid = msg.from_user.id if msg.from_user else None
    _log_bot_reply("cmd_ping", update.effective_chat.id, uid)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return
    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))

    chat_id = update.effective_chat.id
    allowed = settings.allowed_chat_id
    is_allowed = (allowed is None) or (chat_id == allowed)
    bot_username = context.application.bot_data.get("bot_username")

    text = (
        _t(lang, "bot_status") + "\n"
        f"bot: <code>@{html.escape(str(bot_username or ''))}</code>\n"
        f"chat_id: <code>{chat_id}</code>\n"
        f"ALLOWED_CHAT_ID: <code>{'' if allowed is None else allowed}</code>\n"
        f"chat_allowed: <code>{str(is_allowed).lower()}</code>\n"
        f"wiki_docs: <code>{index.doc_count}</code>\n"
        f"QUESTIONS_ONLY: <code>{str(settings.questions_only).lower()}</code>\n"
        f"REQUIRE_TRIGGER: <code>{str(settings.require_trigger).lower()}</code>\n"
        f"RU_LAYER_ENABLED: <code>{str(settings.ru_layer_enabled).lower()}</code>\n"
        f"CLARIFY_ENABLED: <code>{str(settings.clarify_enabled).lower()}</code>\n"
        f"CLARIFY_CORRECTION_MAX: <code>{settings.clarify_correction_max}</code>\n"
        f"CLARIFY_CORRECTION_TTL_SECONDS: <code>{settings.clarify_correction_ttl_seconds}</code>\n"
        f"LOG_DECISIONS: <code>{str(settings.log_decisions).lower()}</code>"
    )
    await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    uid = msg.from_user.id if msg.from_user else None
    _log_bot_reply("cmd_status", chat_id, uid)


async def cmd_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /error — использовать только reply на сообщение бота, чтобы:
    - удалить неверный ответ бота
    - перепоискать ответ
    - запомнить, что тот URL был неверным (локальное обучение)
    """
    if not update.effective_chat or not update.effective_message:
        return
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))
    chat_id = update.effective_chat.id
    uid = msg.from_user.id if msg.from_user else None
    settings = context.application.bot_data["settings"]

    bot_id = context.application.bot_data.get("bot_id")
    if not msg.reply_to_message or not msg.reply_to_message.from_user or bot_id is None or msg.reply_to_message.from_user.id != bot_id:
        await msg.reply_text(_t(lang, "error_usage"), disable_web_page_preview=True)
        _log_bot_reply("cmd_error_usage", chat_id, uid)
        return

    bad_mid = msg.reply_to_message.message_id
    store = context.application.bot_data.setdefault("answer_ctx_store", _load_answer_ctx_store())
    item = store.get(_answer_ctx_key(chat_id, bad_mid)) if isinstance(store, dict) else None
    if not isinstance(item, dict) or not item.get("q"):
        await msg.reply_text(_t(lang, "unknown_reply_ctx"), disable_web_page_preview=True)
        _log_bot_reply("cmd_error_no_ctx", chat_id, uid, bad_mid=bad_mid)
        return

    query = str(item.get("q") or "").strip()
    bad_url = str(item.get("url") or "").strip() or None
    _remember_bad_answer(context=context, query=query, bad_url=bad_url)

    # Удаляем неверный ответ бота (если есть права)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=bad_mid)
    except Exception:
        pass

    # Перепоиск
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    exclude = _excluded_urls_for_query(context=context, query=query)
    variants = expand_queries(query) if settings.ru_layer_enabled else [query]
    best_doc, best_score = _search_best_with_model_bias_excluding(
        index,
        variants,
        context_text=query,
        topic_for_keywords=query,
        exclude_urls=exclude,
        top_k=max(40, int(settings.top_k) * 20),
    )

    if not best_doc or best_score < settings.min_score or not _response_wiki_url_acceptable(query, best_doc.url):
        await msg.reply_text(_t(lang, "error_no_better"), disable_web_page_preview=True)
        _log_bot_reply("cmd_error_no_better", chat_id, uid, score=(best_score if best_doc else None), url=(best_doc.url if best_doc else None))
        return

    title = html.escape(best_doc.title)
    url = best_doc.url
    sent = await msg.reply_text(
        _t(lang, "error_retry") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    _record_bot_answer_context(context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=url)
    _log_bot_reply("cmd_error_retry", chat_id, uid, score=best_score, url=url)


def _extract_url_arg(args: list[str]) -> str | None:
    for a in args or []:
        s = (a or "").strip()
        if s.startswith("http://") or s.startswith("https://"):
            return s
    return None


async def cmd_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /fix <url> — reply на сообщение бота:
    - удаляет старое сообщение бота
    - отправляет "правильную" ссылку
    - запоминает: старый URL плохой, новый — предпочтительный для этого запроса
    """
    if not update.effective_chat or not update.effective_message:
        return
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))
    chat_id = update.effective_chat.id
    uid = msg.from_user.id if msg.from_user else None

    bot_id = context.application.bot_data.get("bot_id")
    if not msg.reply_to_message or not msg.reply_to_message.from_user or bot_id is None or msg.reply_to_message.from_user.id != bot_id:
        await msg.reply_text(_t(lang, "fix_usage_reply"), disable_web_page_preview=True)
        _log_bot_reply("cmd_fix_usage", chat_id, uid)
        return

    good_url = _extract_url_arg(list(context.args or []))
    if not good_url:
        await msg.reply_text(_t(lang, "fix_usage"), disable_web_page_preview=True)
        _log_bot_reply("cmd_fix_usage", chat_id, uid)
        return

    bad_mid = msg.reply_to_message.message_id
    store = context.application.bot_data.setdefault("answer_ctx_store", _load_answer_ctx_store())
    item = store.get(_answer_ctx_key(chat_id, bad_mid)) if isinstance(store, dict) else None
    if not isinstance(item, dict) or not item.get("q"):
        await msg.reply_text(_t(lang, "unknown_reply_ctx"), disable_web_page_preview=True)
        _log_bot_reply("cmd_fix_no_ctx", chat_id, uid, bad_mid=bad_mid)
        return

    query = str(item.get("q") or "").strip()
    bad_url = str(item.get("url") or "").strip() or None

    # учимся: старый URL плохой, новый — предпочтительный
    _remember_bad_answer(context=context, query=query, bad_url=bad_url)
    _remember_good_fix(context=context, query=query, good_url=good_url)

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=bad_mid)
    except Exception:
        pass

    sent = await msg.reply_text(
        _t(lang, "fix_confirm") + "\n"
        f"<a href=\"{html.escape(good_url)}\">{html.escape(good_url)}</a>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    _record_bot_answer_context(context=context, chat_id=chat_id, bot_message_id=sent.message_id, query=query, url=good_url)
    _log_bot_reply("cmd_fix", chat_id, uid, url=good_url)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled error while processing update: %s", context.error)


async def on_any_update(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Диагностика: логируем факт получения любого update, чтобы понять
    приходит ли вообще обычный message в бота.
    """
    settings = context.application.bot_data.get("settings")
    if not settings or not getattr(settings, "log_decisions", False):
        return
    try:
        if isinstance(update, Update):
            kind = (
                "message"
                if update.message
                else "edited_message"
                if update.edited_message
                else "channel_post"
                if update.channel_post
                else "other"
            )
            chat_id = update.effective_chat.id if update.effective_chat else "?"
            uid = update.effective_user.id if update.effective_user else "?"
            txt = None
            reply_mid = None
            reply_from = None
            m = update.effective_message
            if m:
                txt = m.text if m.text is not None else m.caption
                if m.reply_to_message:
                    reply_mid = m.reply_to_message.message_id
                    if m.reply_to_message.from_user:
                        reply_from = m.reply_to_message.from_user.id
            logging.info(
                "update kind=%s chat=%s user=%s has_reply=%s reply_mid=%s reply_from=%s text=%s",
                kind,
                chat_id,
                uid,
                str(bool(m and m.reply_to_message)).lower(),
                reply_mid,
                reply_from,
                (txt or "")[:80],
            )
        else:
            logging.info("update type=%s", type(update).__name__)
    except Exception:
        # не ломаем обработку апдейтов диагностикой
        pass


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if not update.effective_chat:
        return

    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    rl = context.application.bot_data.setdefault(
        "rate_limit",
        {
            "last_reply_ts_by_chat": {},
            "reply_ts_by_chat": {},
            "last_url_ts_by_chat": {},
        },
    )

    chat_id = update.effective_chat.id
    if settings.allowed_chat_id is not None and chat_id != settings.allowed_chat_id:
        if settings.log_decisions:
            logging.info("skip chat=%s reason=not_allowed_chat", chat_id)
        return

    msg = update.effective_message
    if not msg:
        return

    # В группах часто вопросы прилетают как "text", но иногда как подпись к медиа.
    raw_text = msg.text if msg.text is not None else msg.caption
    if not raw_text:
        return

    text = raw_text.strip()
    if not text:
        return

    # Язык ответа: определяем по языку сообщения/пользователя.
    user_lang_code = msg.from_user.language_code if (msg.from_user and getattr(msg.from_user, "language_code", None)) else None
    lang = _detect_user_lang(text=text, user_lang_code=user_lang_code)
    context.application.bot_data["last_user_lang"] = lang

    # Базовая диагностика: если включено LOG_DECISIONS — логируем факт получения сообщения.
    if settings.log_decisions:
        uid = msg.from_user.id if msg.from_user else "?"
        rmid = msg.reply_to_message.message_id if msg.reply_to_message else None
        rfrom = msg.reply_to_message.from_user.id if (msg.reply_to_message and msg.reply_to_message.from_user) else None
        logging.info(
            "seen chat=%s user=%s has_reply=%s reply_mid=%s reply_from=%s text=%s",
            chat_id,
            uid,
            str(bool(msg.reply_to_message)).lower(),
            rmid,
            rfrom,
            text[:120],
        )

    # Если это reply на уточняющий вопрос бота — обработаем отдельно;
    # затем — поправка модели reply на любой ответ бота в той же «сессии».
    if settings.clarify_enabled:
        handled = await _maybe_handle_clarification_followup(update, context)
        if handled:
            return
        if await _maybe_handle_clarify_correction_followup(update, context):
            return

    if settings.log_all_messages:
        logging.info("Входящее сообщение chat=%s user=%s: %s", chat_id, msg.from_user.id if msg.from_user else "?", text[:200])

    # В группах отвечаем только если к нам обратились (упоминание) или это ожидаемый reply на уточнение.
    if settings.require_trigger:
        bot_username = context.application.bot_data.get("bot_username")
        bot_id = context.application.bot_data.get("bot_id")
        if not _is_triggered_message(update, bot_username=bot_username, bot_id=bot_id) and not _reply_is_expected_by_bot(update, context):
            if settings.log_decisions:
                logging.info("skip chat=%s reason=not_triggered", chat_id)
            return

    # Не отвечаем на команды и свои же/сервисные сообщения.
    if text.startswith("/"):
        return

    if settings.questions_only and not index.looks_like_question(text):
        if settings.log_decisions:
            logging.info("skip chat=%s reason=not_a_question", chat_id)
        return

    # Короткий "help" без контекста — просим уточнить, вместо бессмысленного поиска.
    if _is_generic_help_without_context(text):
        await msg.reply_text(
            _t(lang, "generic_help"),
            disable_web_page_preview=True,
        )
        _log_bot_reply("generic_help_clarify", chat_id, msg.from_user.id if msg.from_user else None)
        return

    if await _maybe_reply_printer_design_vs_question(
        msg,
        question=text,
        chat_id=chat_id,
        settings=settings,
        user_id=msg.from_user.id if msg.from_user else None,
    ):
        return

    is_err = _is_error_code_query(text)
    code = _extract_error_code(text)
    if is_err and code:
        candidates = _error_code_candidates(index, code)
        if not candidates:
            # fallback: отдельный каталог ошибок из /en/error-codes + ручные доп. записи
            catalog: dict[str, ErrorCodeInfo] = context.application.bot_data.get("error_codes_catalog", {})
            info = catalog.get(code) if isinstance(catalog, dict) else None
            if info:
                formatted = await _format_error_code_info_ru(context=context, info=info)
                sent = await msg.reply_text(
                    formatted,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                _record_bot_answer_context(
                    context=context,
                    chat_id=chat_id,
                    bot_message_id=sent.message_id,
                    query=text,
                    url=None,
                )
                _log_bot_reply("error_code_text", chat_id, msg.from_user.id if msg.from_user else None, code=code)
                return
            if settings.log_decisions:
                logging.info("skip chat=%s reason=error_code_not_found code=%s", chat_id, code)
            return
        best_doc = _pick_error_code_doc(index, code, context_text=text)
        best_score = 100 if best_doc else -1
        if best_doc is None:
            if await _try_send_error_code_clarify(
                msg=msg,
                context=context,
                chat_id=chat_id,
                text=text,
                code=code,
                candidates=candidates,
                settings=settings,
            ):
                return
            # Если не смогли выбрать и уточнение не отправили — молчим.
            if settings.log_decisions:
                logging.info("skip chat=%s reason=error_code_ambiguous code=%s", chat_id, code)
            return
    else:
        variants = expand_queries(text) if settings.ru_layer_enabled else [text]
        best_doc, best_score = _search_best_with_model_bias(
            index, variants, context_text=text, topic_for_keywords=text
        )

    if not best_doc:
        if settings.log_decisions:
            if is_err and code:
                logging.info("skip chat=%s reason=error_code_not_found code=%s", chat_id, code)
            else:
                logging.info("skip chat=%s reason=no_results docs=%d", chat_id, index.doc_count)
        return
    if best_score < settings.min_score:
        # Для кодов ошибок: либо находим точную страницу по коду, либо молчим (без уточнений).
        if is_err:
            if settings.log_decisions:
                logging.info(
                    "skip chat=%s reason=error_code_not_found score=%d min=%d url=%s",
                    chat_id,
                    best_score,
                    settings.min_score,
                    best_doc.url,
                )
            return
        clarify_low = await _try_send_printer_clarify(
            msg=msg,
            context=context,
            chat_id=chat_id,
            text=text,
            best_doc=best_doc,
            best_score=best_score,
            settings=settings,
            require_score_floor=True,
            score_floor=settings.clarify_min_score,
        )
        if clarify_low in ("sent", "blocked"):
            return

        if settings.log_decisions:
            logging.info("skip chat=%s reason=low_score score=%d min=%d url=%s", chat_id, best_score, settings.min_score, best_doc.url)
        return

    clarify_hi = await _try_send_printer_clarify(
        msg=msg,
        context=context,
        chat_id=chat_id,
        text=text,
        best_doc=best_doc,
        best_score=best_score,
        settings=settings,
        require_score_floor=False,
        score_floor=0,
    )
    if clarify_hi in ("sent", "blocked"):
        return

    url = best_doc.url
    if not _response_wiki_url_acceptable(text, url):
        # Для кодов ошибок не шлём "нет гайда" — просто молчим.
        if is_err:
            if settings.log_decisions:
                logging.info(
                    "skip chat=%s reason=error_code_not_found url=%s",
                    chat_id,
                    url,
                )
            return
        await _reply_no_guide_for_model(
            msg,
            chat_id=chat_id,
            settings=settings,
            user_id=msg.from_user.id if msg.from_user else None,
            best_url=url,
            hints=_model_slug_hints(text),
        )
        return

    # ---- антиспам (на чат) ----
    now = time.time()

    last_reply_ts = rl["last_reply_ts_by_chat"].get(chat_id, 0.0)
    uid_cd = msg.from_user.id if msg.from_user else None
    if uid_cd not in _COOLDOWN_EXEMPT_USERS and now - last_reply_ts < settings.cooldown_seconds:
        if settings.log_decisions:
            logging.info("skip chat=%s reason=cooldown", chat_id)
        return

    q: deque[float] = rl["reply_ts_by_chat"].setdefault(chat_id, deque())
    cutoff = now - 60.0
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= settings.max_replies_per_minute:
        if settings.log_decisions:
            logging.info("skip chat=%s reason=rate_limit", chat_id)
        return

    last_url = rl["last_url_ts_by_chat"].setdefault(chat_id, {})
    last_url_ts = float(last_url.get(url, 0.0))
    if now - last_url_ts < settings.duplicate_window_seconds:
        if settings.log_decisions:
            logging.info("skip chat=%s reason=duplicate url=%s", chat_id, url)
        return

    title = html.escape(best_doc.title)
    score = best_score

    reply = (
        _t(context.application.bot_data.get("last_user_lang") or "ru", "already_in_wiki") + "\n"
        f"• <b>{title}</b>\n"
        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"
        f"<i>{html.escape(_t(context.application.bot_data.get('last_user_lang') or 'ru', 'match').format(score=score))}</i>"
    )

    sent = await msg.reply_text(
        reply,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    uid_r = msg.from_user.id if msg.from_user else None
    _log_bot_reply("wiki", chat_id, uid_r, score=best_score, url=url)
    _record_bot_answer_context(
        context=context,
        chat_id=chat_id,
        bot_message_id=sent.message_id,
        query=text,
        url=url,
    )

    # фиксируем отправку после успешного ответа
    rl["last_reply_ts_by_chat"][chat_id] = now
    q.append(now)
    last_url[url] = now


def main() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "bot.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    # В консоль (окно)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # В файл с ротацией (чтобы не разрастался бесконечно)
    fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.info("Лог-файл: %s", log_path.resolve())
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Подхватываем .env, если он рядом с запуском.
    load_dotenv(override=False)

    settings = load_settings()

    # Простейший лок-файл, чтобы не запустить 2 экземпляра polling одновременно.
    # Храним рядом с кэшем, чтобы путь был "рядом с ботом", а не где-то в системных папках.
    lock_path = Path(settings.cache_path).resolve().parent / "bot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
            try:
                os.kill(old_pid, 0)
                raise RuntimeError(
                    f"Похоже, бот уже запущен (pid={old_pid}). Остановите старый процесс и запустите снова."
                )
            except OSError:
                pass
        except Exception:
            pass
    lock_path.write_text(str(os.getpid()), encoding="utf-8")

    wiki_index = WebWikiIndex.empty()
    indexer = WebWikiIndexer(
        index=wiki_index,
        cache_path=settings.cache_path,
        state_path=settings.state_path,
        sitemap_url=settings.wiki_sitemap_url,
        base_url=settings.wiki_base_url,
        max_pages=settings.wiki_max_pages,
    )
    indexer.load_cached_docs()

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["wiki_index"] = wiki_index
    app.bot_data["wiki_indexer"] = indexer
    # восстанавливаем ожидаемые уточнения после перезапуска
    try:
        store = _load_clarify_store()
        pending2: dict[tuple[int, int], dict] = {}
        for k, v in store.items():
            try:
                chat_s, user_s = k.split(":", 1)
                pending2[(int(chat_s), int(user_s))] = v
            except Exception:
                continue
        app.bot_data["clarify_pending"] = pending2
    except Exception:
        app.bot_data["clarify_pending"] = {}

    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("wiki", cmd_wiki))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("error", cmd_error))
    app.add_handler(CommandHandler("fix", cmd_fix))
    # Диагностика: первым делом логируем любой update
    app.add_handler(TypeHandler(Update, on_any_update), group=-1)
    # filters.UpdateType.* здесь не используем, чтобы не "отрезать" обычные сообщения.
    # Без & ~filters.COMMAND: на части апдейтов (пустой text/caption) комбинация ломалась на PTB 21 + Py 3.14.
    # Команды всё равно отсекаются в on_message по префиксу "/" и отдельными CommandHandler.
    app.add_handler(MessageHandler((filters.TEXT | filters.Caption), on_message))
    app.add_error_handler(on_error)

    logging.info("Бот запущен. Wiki docs: %d", wiki_index.doc_count)

    async def _post_init(application: Application) -> None:
        me = await application.bot.get_me()
        application.bot_data["bot_username"] = me.username
        application.bot_data["bot_id"] = me.id
        logging.info("Bot username: @%s", me.username)
        # Каталог ошибок (fallback, если у кода нет отдельной страницы /error-codes/<code>-code)
        try:
            manual = _load_manual_error_codes()
            scraped = await ensure_error_codes_catalog(
                base_url=settings.wiki_base_url,
                cache_path=".cache/error_codes_catalog.json",
                refresh_hours=max(1, int(settings.wiki_refresh_hours)),
            )
            application.bot_data["error_codes_catalog"] = merge_manual_overrides(scraped, manual)
            logging.info(
                "Каталог кодов ошибок загружен: %d (manual=%d)",
                len(application.bot_data["error_codes_catalog"]),
                len(manual),
            )
        except Exception as e:
            logging.warning("Не удалось загрузить каталог кодов ошибок: %s", e)
        # Локальные фиксы ссылок (/fix)
        try:
            application.bot_data["fix_store"] = _load_fix_store()
            logging.info("Fix-store загружен: %d", len(application.bot_data["fix_store"]))
        except Exception as e:
            logging.warning("Не удалось загрузить fix-store: %s", e)

    async def _index_step(context) -> None:
        _ = context
        idxr: WebWikiIndexer = app.bot_data["wiki_indexer"]
        st = app.bot_data["settings"]
        if idxr.is_done():
            # Если уже всё скачано — попробуем один раз отправить уведомление (если включено).
            if (
                st.notify_on_index_done
                and st.notify_chat_id is not None
                and not idxr.is_done_notified()
            ):
                mention = (st.notify_mention or "").strip()
                text = "Индексация вики завершена."
                if mention:
                    text = f"{mention} {text}"
                try:
                    await app.bot.send_message(chat_id=st.notify_chat_id, text=text)
                    idxr.mark_done_notified()
                    logging.info("Отправлено уведомление о завершении индексации в чат %s", st.notify_chat_id)
                except Exception as e:
                    logging.warning("Не удалось отправить уведомление: %s", e)
            # Всё готово — отключаем дальнейшие запуски job, чтобы не спамить логами.
            job = app.bot_data.get("index_job")
            try:
                if job:
                    job.schedule_removal()
                    app.bot_data["index_job"] = None
                    logging.info("Индексация завершена — job index_step отключён")
            except Exception:
                pass
            return
        t0 = time.time()
        # step() блокирующий (httpx sync), выполняем в отдельном потоке
        await asyncio.to_thread(idxr.step, st.index_batch_size)
        dt = time.time() - t0

        # Если после шага всё закончилось — тоже уведомим.
        if (
            idxr.is_done()
            and st.notify_on_index_done
            and st.notify_chat_id is not None
            and not idxr.is_done_notified()
        ):
            mention = (st.notify_mention or "").strip()
            text = "Индексация вики завершена."
            if mention:
                text = f"{mention} {text}"
            try:
                await app.bot.send_message(chat_id=st.notify_chat_id, text=text)
                idxr.mark_done_notified()
                logging.info("Отправлено уведомление о завершении индексации в чат %s", st.notify_chat_id)
            except Exception as e:
                logging.warning("Не удалось отправить уведомление: %s", e)

        # Если индексация завершилась на этом шаге — отключаем job.
        if idxr.is_done():
            job = app.bot_data.get("index_job")
            try:
                if job:
                    job.schedule_removal()
                    app.bot_data["index_job"] = None
                    logging.info("Индексация завершена — job index_step отключён")
            except Exception:
                pass
            return

        if not st.auto_tune_indexer:
            return

        # Автоподстройка интервала: если шаг занимает почти весь интервал — увеличиваем.
        # Если шаг очень быстрый — слегка уменьшаем (но не ниже минимума).
        cur = float(app.bot_data.get("index_interval_current", st.index_interval_seconds))
        new = cur
        if dt > cur * 0.9:
            new = min(float(st.index_interval_max_seconds), max(cur, dt * 1.5))
        elif dt < cur * 0.25:
            new = max(float(st.index_interval_min_seconds), cur * 0.8)

        # Если интервал меняется заметно — пересоздаём job.
        if abs(new - cur) >= 2.0:
            app.bot_data["index_interval_current"] = new
            job = app.bot_data.get("index_job")
            try:
                if job:
                    job.schedule_removal()
            except Exception:
                pass
            app.bot_data["index_job"] = app.job_queue.run_repeating(
                _index_step,
                interval=int(round(new)),
                first=int(round(new)),
                name="index_step",
            )
            logging.info("Автоподстройка: шаг %.1fs -> новый интервал %ss", dt, int(round(new)))

    # Периодически докачиваем новые страницы, прогресс сохраняется в .cache/
    app.bot_data["index_interval_current"] = float(settings.index_interval_seconds)
    app.bot_data["index_job"] = app.job_queue.run_repeating(
        _index_step,
        interval=settings.index_interval_seconds,
        first=1,
        name="index_step",
    )
    app.post_init = _post_init  # type: ignore[attr-defined]
    # Важно: после перезапуска не "догоняем" накопившиеся сообщения.
    # Telegram отдаёт накопленные updates при polling — drop_pending_updates их сбрасывает.
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    # Нужен для Windows при запуске как скрипта.
    os.environ.setdefault("PYTHONUTF8", "1")
    # На некоторых версиях Python/Windows PTB может не найти loop, если его не создать заранее.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()
