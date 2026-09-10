"""
Контекст диалога: история сообщений пользователей, обогащение поисковых запросов.

Три уровня:
  1. Сообщения пользователя — последние 8, TTL 30 мин.
  2. Ответы бота пользователю — последние 4, TTL 30 мин.
  3. Сообщения чата (все пользователи) — последние 15, TTL 10 мин.

Обогащение запроса срабатывает когда:
  - запрос содержит анафору / местоимения (его, её, там, это, …)
  - ИЛИ запрос очень короткий (≤ 3 слова)

Persist: .cache/user_ctx.json, атомарная запись, не чаще раза в минуту.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.bot.stores import _save_json_atomic

# ── константы ────────────────────────────────────────────────────────────────

_USER_MSG_MAX  = 8      # последних сообщений на пользователя
_BOT_ANS_MAX   = 4      # последних ответов бота пользователю
_CHAT_MSG_MAX  = 15     # последних сообщений в чате
_USER_TTL      = 1800   # с — TTL пользовательского контекста (30 мин)
_CHAT_TTL      = 600    # с — TTL чатового контекста (10 мин)
_SHORT_WORDS   = 3      # запрос ≤ N слов → обогащать всегда
_CTX_WORDS_MAX = 6      # макс. добавляемых контекстных слов

# Слова-триггеры анафоры: указывают на необходимость контекста
_ANAPHORA_RU: frozenset[str] = frozenset({
    "его", "её", "ее", "это", "этого", "этому", "этим", "этой",
    "этот", "эта", "эти", "там", "туда", "тут", "оно", "они",
    "их", "им", "ими", "он", "она", "такое", "такого", "такой",
    "таком", "таким", "тот", "та", "те", "то", "тем", "тех",
    "данный", "данная", "данное", "данные", "данного", "выше", "ниже",
})

# Стоп-слова для извлечения ключевых слов из истории
_STOP_RU: frozenset[str] = frozenset({
    "а", "вот", "как", "и", "в", "на", "по", "с", "к", "у", "из",
    "от", "до", "за", "но", "или", "что", "это", "я", "ты", "он",
    "она", "мы", "вы", "они", "нет", "да", "не", "же", "бы", "ли",
    "уже", "ещё", "только", "вообще", "тоже", "там", "здесь", "так",
    "очень", "более", "менее", "можно", "надо", "нужно", "хочу",
    "помогите", "помоги", "подскажите", "подскажи", "скажите", "скажи",
    "будет", "был", "была", "было", "есть", "быть", "привет",
    "спасибо", "пожалуйста", "тогда", "ведь", "раз", "про", "уж",
})

_SAVE_INTERVAL = 60.0   # с — не чаще раза в минуту
_SAVE_LOCK     = threading.Lock()


def _fresh_context_items(items: list[object], *, now: float, ttl: float) -> list[dict[str, Any]]:
    """Возвращает только корректные и неистёкшие записи контекста."""
    fresh: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if _is_fresh_context_item(item, now=now, ttl=ttl):
            fresh.append(item)
    return fresh


def _is_fresh_context_item(item: dict[str, Any], *, now: float, ttl: float) -> bool:
    try:
        timestamp = float(item.get("ts", 0))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(timestamp) and now - timestamp < ttl


def _dict_store(bot_data: dict[str, Any], key: str) -> dict[str, Any]:
    store = bot_data.get(key)
    if not isinstance(store, dict):
        store = {}
        bot_data[key] = store
    return store


def _list_buffer(store: dict[str, Any], key: str) -> list[dict[str, Any]]:
    buffer = store.get(key)
    if not isinstance(buffer, list):
        buffer = []
        store[key] = buffer
    return buffer


# ── пути и диск ───────────────────────────────────────────────────────────────

def _ctx_path() -> Path:
    from app.bot.git_autopull import project_repo_root
    return project_repo_root() / ".cache" / "user_ctx.json"


def _ensure_loaded(bot_data: dict[str, Any]) -> None:
    """Ленивая загрузка с диска при первом обращении."""
    if bot_data.get("_user_ctx_loaded"):
        return
    _load_from_disk(bot_data)
    bot_data["_user_ctx_loaded"] = True


def _load_from_disk(bot_data: dict[str, Any]) -> None:
    try:
        p = _ctx_path()
        if not p.exists():
            return
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return
        now = time.time()
        for src_key, dst_key, ttl, max_n in [
            ("users",       "user_ctx_msgs",    _USER_TTL, _USER_MSG_MAX),
            ("bot_answers", "user_ctx_answers", _USER_TTL, _BOT_ANS_MAX),
        ]:
            src = raw.get(src_key, {})
            if not isinstance(src, dict):
                continue
            dst = _dict_store(bot_data, dst_key)
            for k, v in src.items():
                if not isinstance(v, list):
                    continue
                fresh = _fresh_context_items(v, now=now, ttl=ttl)
                if fresh:
                    buf = _list_buffer(dst, k)
                    buf[:] = [m for m in buf if isinstance(m, dict)]
                    existing_ts = {m.get("ts") for m in buf}
                    for m in fresh:
                        if m.get("ts") not in existing_ts:
                            buf.append(m)
                            existing_ts.add(m.get("ts"))
                    buf[:] = buf[-max_n:]
    except Exception:
        pass


def save_ctx_to_disk(bot_data: dict[str, Any], *, force: bool = False) -> None:
    """Сохраняет контекст на диск атомарно, не чаще раза в минуту."""
    now = time.time()
    if not force and now - bot_data.get("_user_ctx_last_save", 0.0) < _SAVE_INTERVAL:
        return
    with _SAVE_LOCK:
        if not force and now - bot_data.get("_user_ctx_last_save", 0.0) < _SAVE_INTERVAL:
            return
        try:
            p = _ctx_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "users":       dict(bot_data.get("user_ctx_msgs", {})),
                "bot_answers": dict(bot_data.get("user_ctx_answers", {})),
            }
            _save_json_atomic(p, data)
            bot_data["_user_ctx_last_save"] = now
        except Exception:
            pass


# ── утилиты ───────────────────────────────────────────────────────────────────

def _ukey(user_id: int, chat_id: int) -> str:
    return f"{chat_id}:{user_id}"


def _words(text: str) -> list[str]:
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower(), flags=re.UNICODE)
    return [w for w in cleaned.split() if w and len(w) >= 3 and w not in _STOP_RU]


def _has_anaphora(text: str) -> bool:
    return bool(set(text.lower().split()) & _ANAPHORA_RU)


# ── публичный API ─────────────────────────────────────────────────────────────

def record_user_message(
    bot_data: dict[str, Any],
    *,
    user_id: int,
    chat_id: int,
    text: str,
) -> None:
    """Записывает сообщение пользователя в его историю и в историю чата."""
    _ensure_loaded(bot_data)
    now = time.time()
    ukey = _ukey(user_id, chat_id)

    # Пользовательская история
    msgs = _dict_store(bot_data, "user_ctx_msgs")
    buf = _list_buffer(msgs, ukey)
    buf.append({"text": text[:500], "ts": now})
    buf[:] = _fresh_context_items(buf, now=now, ttl=_USER_TTL)
    if len(buf) > _USER_MSG_MAX:
        del buf[:-_USER_MSG_MAX]

    # История чата (все пользователи)
    chat_msgs = _dict_store(bot_data, "chat_ctx_msgs")
    cbuf = _list_buffer(chat_msgs, str(chat_id))
    cbuf.append({"user_id": user_id, "text": text[:300], "ts": now})
    cbuf[:] = _fresh_context_items(cbuf, now=now, ttl=_CHAT_TTL)
    if len(cbuf) > _CHAT_MSG_MAX:
        del cbuf[:-_CHAT_MSG_MAX]

    save_ctx_to_disk(bot_data)


def record_bot_answer(
    bot_data: dict[str, Any],
    *,
    user_id: int,
    chat_id: int,
    answer_text: str,
    url: str = "",
) -> None:
    """Запоминает ответ бота пользователю (для обогащения последующих запросов)."""
    _ensure_loaded(bot_data)
    now = time.time()
    ukey = _ukey(user_id, chat_id)
    ans = _dict_store(bot_data, "user_ctx_answers")
    buf = _list_buffer(ans, ukey)
    buf.append({"text": answer_text[:300], "url": url, "ts": now})
    buf[:] = _fresh_context_items(buf, now=now, ttl=_USER_TTL)
    if len(buf) > _BOT_ANS_MAX:
        del buf[:-_BOT_ANS_MAX]
    save_ctx_to_disk(bot_data)


def enrich_query(
    bot_data: dict[str, Any],
    *,
    user_id: int,
    chat_id: int,
    query: str,
) -> str:
    """
    Обогащает поисковый запрос контекстом диалога.

    Если запрос содержит анафору (его, там, это…) или очень короткий —
    добавляет ключевые слова из истории: ответы бота → сообщения пользователя → чат.

    Возвращает enriched строку (исходный запрос добавлен в конец).
    Если контекст не нужен или не найден — возвращает query без изменений.
    """
    _ensure_loaded(bot_data)
    # Если в запросе нет реальных слов (только числа/символы — «35?», «40%?»),
    # обогащение только навредит: добавит слова из контекста и заставит бота
    # ответить на бессмысленный числовой фрагмент.
    if not _words(query):
        return query
    needs_ctx = _has_anaphora(query) or len(query.split()) <= _SHORT_WORDS
    if not needs_ctx:
        return query

    now = time.time()
    ukey = _ukey(user_id, chat_id)

    # Слова из прошлых ответов бота (самые релевантные — бот уже нашёл тему)
    ans_words: list[str] = []
    for a in reversed(bot_data.get("user_ctx_answers", {}).get(ukey, [])[-2:]):
        if not _is_fresh_context_item(a, now=now, ttl=_USER_TTL):
            continue
        ans_words.extend(_words(a.get("text", "")))

    # Слова из предыдущих сообщений пользователя (исключаем текущий)
    user_words: list[str] = []
    for m in reversed(bot_data.get("user_ctx_msgs", {}).get(ukey, [])[-4:-1]):
        if not _is_fresh_context_item(m, now=now, ttl=_USER_TTL):
            continue
        user_words.extend(_words(m.get("text", "")))

    # Слова из контекста чата (другие пользователи — тема разговора)
    chat_words: list[str] = []
    for m in reversed(bot_data.get("chat_ctx_msgs", {}).get(str(chat_id), [])[-5:]):
        if not _is_fresh_context_item(m, now=now, ttl=_CHAT_TTL):
            continue
        if m.get("user_id") == user_id:
            continue  # уже взяли из user_words
        chat_words.extend(_words(m.get("text", "")))

    # Уникальные контекстные слова (приоритет: ответы > сообщения > чат)
    query_words_set = set(_words(query))
    seen = set(query_words_set)
    extras: list[str] = []
    for w in ans_words + user_words + chat_words:
        if w not in seen and len(w) >= 4:
            seen.add(w)
            extras.append(w)
        if len(extras) >= _CTX_WORDS_MAX:
            break

    return (" ".join(extras) + " " + query) if extras else query


def get_user_topic_hint(
    bot_data: dict[str, Any],
    *,
    user_id: int,
    chat_id: int,
) -> str:
    """
    Возвращает строку из ключевых слов текущей темы пользователя
    (для диагностики / логирования).
    """
    _ensure_loaded(bot_data)
    now = time.time()
    ukey = _ukey(user_id, chat_id)

    words: list[str] = []
    for bucket_key, ttl in [
        ("user_ctx_answers", _USER_TTL),
        ("user_ctx_msgs",    _USER_TTL),
    ]:
        for m in reversed(bot_data.get(bucket_key, {}).get(ukey, [])[-3:]):
            if not _is_fresh_context_item(m, now=now, ttl=ttl):
                continue
            words.extend(_words(m.get("text", "")))

    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w not in seen and len(w) >= 4:
            seen.add(w)
            result.append(w)
        if len(result) >= 5:
            break
    return " / ".join(result) if result else ""
