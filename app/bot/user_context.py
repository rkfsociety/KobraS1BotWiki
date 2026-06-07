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
import re
import threading
import time
from pathlib import Path
from typing import Any

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
            dst: dict[str, list] = bot_data.setdefault(dst_key, {})
            for k, v in src.items():
                if not isinstance(v, list):
                    continue
                fresh = [
                    m for m in v
                    if isinstance(m, dict) and now - float(m.get("ts", 0)) < ttl
                ]
                if fresh:
                    existing_ts = {m.get("ts") for m in dst.get(k, [])}
                    buf = dst.setdefault(k, [])
                    for m in fresh:
                        if m.get("ts") not in existing_ts:
                            buf.append(m)
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
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            tmp.replace(p)
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
    msgs: dict[str, list] = bot_data.setdefault("user_ctx_msgs", {})
    buf = msgs.setdefault(ukey, [])
    buf.append({"text": text[:500], "ts": now})
    buf[:] = [m for m in buf if now - m["ts"] < _USER_TTL]
    if len(buf) > _USER_MSG_MAX:
        del buf[:-_USER_MSG_MAX]

    # История чата (все пользователи)
    chat_msgs: dict[str, list] = bot_data.setdefault("chat_ctx_msgs", {})
    cbuf = chat_msgs.setdefault(str(chat_id), [])
    cbuf.append({"user_id": user_id, "text": text[:300], "ts": now})
    cbuf[:] = [m for m in cbuf if now - m["ts"] < _CHAT_TTL]
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
    ans: dict[str, list] = bot_data.setdefault("user_ctx_answers", {})
    buf = ans.setdefault(ukey, [])
    buf.append({"text": answer_text[:300], "url": url, "ts": now})
    buf[:] = [m for m in buf if now - m["ts"] < _USER_TTL]
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
    needs_ctx = _has_anaphora(query) or len(query.split()) <= _SHORT_WORDS
    if not needs_ctx:
        return query

    now = time.time()
    ukey = _ukey(user_id, chat_id)

    # Слова из прошлых ответов бота (самые релевантные — бот уже нашёл тему)
    ans_words: list[str] = []
    for a in reversed(bot_data.get("user_ctx_answers", {}).get(ukey, [])[-2:]):
        if now - float(a.get("ts", 0)) > _USER_TTL:
            continue
        ans_words.extend(_words(a.get("text", "")))

    # Слова из предыдущих сообщений пользователя (исключаем текущий)
    user_words: list[str] = []
    for m in reversed(bot_data.get("user_ctx_msgs", {}).get(ukey, [])[-4:-1]):
        if now - float(m.get("ts", 0)) > _USER_TTL:
            continue
        user_words.extend(_words(m.get("text", "")))

    # Слова из контекста чата (другие пользователи — тема разговора)
    chat_words: list[str] = []
    for m in reversed(bot_data.get("chat_ctx_msgs", {}).get(str(chat_id), [])[-5:]):
        if now - float(m.get("ts", 0)) > _CHAT_TTL:
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
            if now - float(m.get("ts", 0)) > ttl:
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
