from __future__ import annotations



import json
import copy
import hashlib
import logging
import os
import random
import shutil
import tempfile
import time

import re
import xml.etree.ElementTree as ET

from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from heapq import nlargest

from pathlib import Path

from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser



import httpx

from bs4 import BeautifulSoup

from rapidfuzz import fuzz

import threading





from app.bot.text_heuristics import (
    _is_marketplace_promo_message,
    _is_non_wiki_chatter_message,
)



def _normalize(text: str) -> str:

    return " ".join(text.lower().split())


@lru_cache(maxsize=4096)
def _normalize_query(text: str) -> str:
    """Кэширует только короткие пользовательские запросы, не тексты документов."""
    return _normalize(text)





# Для бонуса по пересечению токенов (не считать «общие» слова из каждого URL).

_TOKEN_BONUS_STOP = frozenset(

    {

        "the",

        "and",

        "for",

        "how",

        "what",

        "when",

        "where",

        "why",

        "can",

        "could",

        "with",

        "this",

        "that",

        "from",

        "into",

        "anycubic",

        "wiki",

        "en",

        "guide",

        "video",

        "tutorial",

        "operation",

        "you",

        "your",

        "are",

        "not",

        "but",

        "all",

        "any",

    }

)





def _url_path_words(url: str) -> str:

    """Слова из пути URL (дефисы → пробелы): совпадения с запросом сильнее, чем у короткого title."""

    try:

        parts = [p for p in urlparse(url).path.strip("/").split("/") if p]

    except Exception:

        return ""

    if parts and len(parts[0]) <= 5 and parts[0].isalpha():

        parts = parts[1:]

    words: list[str] = []

    for seg in parts:

        words.extend(seg.replace("-", " ").split())

    return _normalize(" ".join(words))





def _make_search_blob(doc: WebWikiDoc) -> str:

    u = _url_path_words(doc.url)

    if not u:

        return doc.text

    return _normalize(doc.text + " " + u + " " + u.replace(" ", "-"))





@lru_cache(maxsize=4096)
def _looks_like_question(text: str) -> bool:

    if _is_marketplace_promo_message(text):

        return False

    if _is_non_wiki_chatter_message(text):

        return False

    t = _normalize_query(text)

    if "?" in text:

        return True

    # Сообщения вида "Ошибка 11518" / "11518" считаем вопросом (поиск по кодам ошибок).

    # Важно: слово "ошибка" само по себе НЕ считаем вопросом (напр. "ошибка природы").

    if re.search(r"\b\d{4,7}\b", t) and ("ошибк" in t or "error" in t or "err" in t):

        return True

    # Фразы вроде "уже не помнит как ..." — это скорее комментарий, а не вопрос к боту.

    # В режиме QUESTIONS_ONLY такие сообщения лучше игнорировать, если нет явного "?",

    # иначе бот будет "влезать" в разговор.

    if re.search(r"\b(уже\s+)?не\s+помнит\s+как\b", t):

        return False

    if re.search(r"\bужас\s+как\b", t) and "?" not in text:

        return False

    if re.search(r"\bкак\s+на\b", t) and not re.search(
        r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)\b", t
    ):

        return False

    # «лучше чем на кобре», «выглядит лучше» — сравнение, не вопрос к боту.
    if re.search(r"\b(?:лучше|хуже)\b", t) and re.search(r"\b(?:чем|как)\s+на\b", t) and "?" not in text:
        if not re.search(
            r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)\b", t
        ):
            return False

    if re.search(r"\bвыглядит\s+(?:лучше|хуже)\b", t) and "?" not in text:
        if re.search(r"\b(?:чем|как)\s+на\b", t) or re.search(r"\bстол\w*\b", t):
            if not re.search(
                r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)\b", t
            ):
                return False

    # «до того как стол крутил» — союзное «как», не «как настроить».
    if re.search(r"\b(?:до|после|перед)\s+того\s+как\b", t) and "?" not in text:
        if not re.search(
            r"\bкак\s+(?:откалибр|настро|почин|исправ|сделать|убрать|решить|подключ|замен)\b", t
        ):
            return False

    if re.search(r"\b(кинь|скинь|дай|подкинь|киньте|скиньте|дайте)\w*\b.{0,20}\bссыл", t):

        return True

    if "ссыл" in t and any(w in t for w in ("вики", "wiki", "настрой", "калибр", "уровн", "стол", "куб")):

        return True

    if re.search(r"\bтак\s+что\b", t) and "?" not in text:
        if not re.search(r"\bтак\s+что\s+(?:делать|значит|не\s+так|не\s+работает)\b", t):
            return False

    if re.search(r"\b(?:сомневаюсь|сомневаемся)\b", t) and re.search(r"\bчто\b", t) and "?" not in text:
        return False

    # «Ну что, запускаю слой» — не вопросительное «что».
    if re.search(r"^ну\s+что\b", t) and "?" not in text:
        if not re.search(r"\bчто\s+(?:делать|значит|не\s+так|не\s+работает)\b", t):
            return False

    # «Нуу, что могу сказать» / «зачем оно тебе» — сарказм в треде, не вопрос к боту.
    if re.search(r"\bчто\s+могу\s+сказать\b", t) and "?" not in text:
        return False
    if re.search(r"\bзачем\s+(?:оно|тебе|вам|это|мне|нам|ему|ей|им|ем)\b", t):
        if "?" not in text and re.search(r"\b(?:спал\s+бы|спи\s+бы|не\s+знал\s+про|что\s+могу\s+сказать)\b", t):
            return False
        if re.search(r"\bговорит\b", t) and re.search(r"\b(?:аська\w*|аськ\w*|многоцвет)\w*\b", t):
            return False

    # «зачем для кобры orca?» — мнение, не вопрос к боту.
    if re.search(r"\bзачем\s+(?:для|у)\s+кобр\w*\b", t) and re.search(r"\b(?:orca|орка|слайсер)\b", t):
        return False

    # «как раздавая акция» — союзное «как», не вопрос к боту.
    if re.search(r"\bкак\s+(?:раздавая|акци\w*)\b", t) and "?" not in text:
        return False

    # «с тем, что напечатала кобра» — союзное «что», не вопрос к боту.
    if re.search(r"\bчто\s+напечатал\w*\b", t) and "?" not in text:
        if re.search(r"\bсравн\w*\b", t) or re.search(r"\bради\s+интереса\b", t):
            return False

    # «А я говорил про …?» — риторика в треде, не вопрос к боту.
    if re.search(r"\b(?:а\s+)?я\s+говорил\s+про\b", t) and "?" in text:
        return False

    # «кобра 3 стоит как Х» — союзное «как», не вопрос к боту.
    if re.search(r"\bстоит\s+как\b", t) and "?" not in text:
        if re.search(r"\b(?:kobra|кобр|vyper|вайпер|photon|фотон)\b", t):
            return False

    # «смотря как купил», «ты говорил…» — бытовой тред, не вопрос к боту.
    if "?" not in text and re.search(r"\b(?:смотря|зависит)\s+как\b", t) and re.search(r"\bкупил\w*\b", t):
        return False
    if "?" not in text and re.search(r"\bты\s+говорил\b", t):
        return False

    # «как они так печатают… на видео кажется» — риторика в чате.
    if re.search(r"\b(?:как\s+они|они\s+так)\b", t) and re.search(r"\bпечата\w*\b", t):
        if re.search(r"\b(?:не\s+похож\w*|на\s+видео)\b", t):
            return False

    # «как кобра х» — обрывок сравнения, не вопрос к боту.
    if re.match(
        r"^как\s+(?:кобр\w*|kobra\w*|vyper\w*|вайпер\w*|фотон\w*)"
        r"(?:\s+\w{1,4})?\s*$",
        t,
        re.I | re.UNICODE,
    ):
        return False

    # «в чате по чиди увидел инфу, что…» — пересказ, не вопрос к боту.
    if re.search(r"\b(?:в\s+чате|в\s+чат\w*)\b", t) and re.search(
        r"\b(?:по\s+)?(?:чиди|чити|chitu)\b", t
    ):
        if re.search(r"\b(?:увидел\w*|увил\w*|инфу|информац)\b", t) or re.search(r"\bчто\b", t):
            return False

    # «как я понял, в аське 2 тоже» — наблюдение, не вопрос «как».
    if re.search(r"\bкак\s+я\s+понял\b", t) and re.search(r"\b(?:чиди|чити|chitu|аська|ace)\b", t):
        return False

    # «кто-то наигрался с многоцветом» — не вопрос «кто».
    if re.search(r"\b(?:кто[-\s]?то|ктото)\b", t) and re.search(r"\b(?:многоцвет|наиграл\w*)\w*\b", t):
        return False

    # «когда первый раз разбирал экструдер на п2с» — история, не вопрос «когда».
    if re.search(r"\bкогда\s+первый\s+раз\b", t) and re.search(r"\bэкструдер\w*\b", t):
        if re.search(r"\b(?:bambu|бамбук|п2с|p2s|нажрал\w*|разобр\w*)\b", t):
            return False

    return bool(
        re.search(
            r"\b(как|почему|зачем|что|где|когда|кто|можно ли|помогите|не работает)\b",
            t,
        )
    )





@dataclass(frozen=True, slots=True)

class WebWikiDoc:

    title: str

    url: str

    text: str





_SEARCH_CACHE_SIZE = 500
_ERROR_CODE_URL_RE = re.compile(r"/error-codes/(?P<code>\d+)-code(?:/|$)", re.IGNORECASE)
_INDEX_CACHE_VERSION = 2
_CHECKPOINT_FORMAT = "anycubic-wiki-index"
_CHECKPOINT_VERSION = 1
_MAX_INDEX_CACHE_BYTES = 64 * 1024 * 1024
_MAX_SITEMAP_BYTES = 16 * 1024 * 1024
_MAX_WIKI_PAGE_BYTES = 16 * 1024 * 1024
_MAX_WIKI_QUEUE_URLS = 50000
_MAX_REDIRECTS = 5
_WIKI_USER_AGENT = "WikiLinkBot/1.0"
_MIN_WIKI_REQUEST_INTERVAL_SECONDS = 1.0
_DEFAULT_EXTRA_WIKI_URLS = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/anycubic-kobra-x",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-4-combo",
)


def _build_error_code_docs(docs: tuple[WebWikiDoc, ...]) -> dict[str, list[WebWikiDoc]]:
    result: dict[str, list[WebWikiDoc]] = {}
    for doc in docs:
        match = _ERROR_CODE_URL_RE.search(doc.url or "")
        if match:
            result.setdefault(match.group("code"), []).append(doc)
    return result


class WebWikiIndex:

    def __init__(self, docs: list[WebWikiDoc]) -> None:

        self._docs = tuple(docs)

        self._error_code_docs = _build_error_code_docs(self._docs)

        self._blobs = tuple(_make_search_blob(d) for d in self._docs)

        # URL-признаки неизменяемы до add_docs/replace_docs: не понижаем URL
        # заново для каждого документа при каждом поисковом запросе.
        self._url_lower = tuple((d.url or "").lower() for d in self._docs)

        # Блобы неизменяемы до add_docs/replace_docs: не разбираем их
        # заново в set на каждом поисковом запросе.
        self._blob_tokens = tuple(frozenset(blob.split()) for blob in self._blobs)

        self._lock = threading.Lock()
        self._version = 0

        self._search_cache: OrderedDict[str, list[tuple[WebWikiDoc, int]]] = OrderedDict()



    @property

    def doc_count(self) -> int:

        with self._lock:

            return len(self._docs)

    def error_code_candidates(self, code: str) -> list[WebWikiDoc]:
        """Возвращает страницы кода без полного прохода по индексу."""
        with self._lock:
            return list(self._error_code_docs.get(str(code), ()))



    @staticmethod

    def looks_like_question(text: str) -> bool:

        return _looks_like_question(text)



    @staticmethod

    def empty() -> "WebWikiIndex":

        return WebWikiIndex([])



    def _score_one(
        self,
        q: str,
        doc: WebWikiDoc,
        blob: str,
        q_tokens: set[str] | None = None,
        b_tokens: frozenset[str] | set[str] | None = None,
        query_flags: tuple[bool, bool, bool] | None = None,
        url_lower: str | None = None,
    ) -> int:

        if not q:

            return 0

        ts = int(fuzz.token_set_ratio(q, blob))

        tr = int(fuzz.token_sort_ratio(q, blob))

        pr = int(fuzz.partial_ratio(q, blob))

        base = int(0.52 * ts + 0.33 * tr + 0.15 * pr)



        if q_tokens is None:
            q_tokens = {t for t in q.split() if len(t) > 2 and t not in _TOKEN_BONUS_STOP}
        if b_tokens is None:
            b_tokens = set(blob.split())
        if query_flags is None:
            query_flags = (
                any(k in q for k in ("replac", "install", "remov", "swap", "chang", "disassembl")),
                any(k in q for k in ("extrud", "hotend", "nozzle", "print-head", "printhead")),
                "kobra" in q,
            )
        is_replacement_query, is_component_query, has_kobra = query_flags
        normalized_url = (doc.url or "").lower() if url_lower is None else url_lower

        overlap = len(q_tokens & b_tokens)

        bonus = min(26, overlap * 5)



        if is_replacement_query:

            if "replacement" in normalized_url or "replace" in normalized_url or "install" in normalized_url:

                bonus += 10



        if is_component_query:

            if "/faq" in normalized_url or normalized_url.rstrip("/").endswith("/faq"):

                bonus -= 14



        if has_kobra and "kobra" in blob:

            bonus += 8

        if "s1" in q_tokens and "s1" in b_tokens:

            bonus += 8

        if "combo" in q_tokens and "combo" in b_tokens:

            bonus += 8



        return max(0, min(100, base + bonus))



    def search(self, query: str, *, top_k: int = 1) -> list[tuple[WebWikiDoc, int]]:

        q = _normalize_query(query)
        if not q:
            return []
        limit = max(1, top_k)
        cache_key = q

        with self._lock:
            cached = self._search_cache.get(cache_key)
            if cached is not None and len(cached) >= limit:
                self._search_cache.move_to_end(cache_key)
                # Не отдаём внутренний список: вызывающий код может изменить его
                # и тем самым повредить результат для следующих запросов.
                return list(cached[:limit])
            # Коллекции immutable: snapshot — это только несколько ссылок,
            # без копирования всего индекса под lock.
            blobs = self._blobs
            blob_tokens = self._blob_tokens
            url_lower = self._url_lower
            docs = self._docs
            version = self._version

        q_tokens = {t for t in q.split() if len(t) > 2 and t not in _TOKEN_BONUS_STOP}
        query_flags = (
            any(k in q for k in ("replac", "install", "remov", "swap", "chang", "disassembl")),
            any(k in q for k in ("extrud", "hotend", "nozzle", "print-head", "printhead")),
            "kobra" in q,
        )
        scored = (
            (
                self._score_one(q, docs[i], blob, q_tokens, blob_tokens[i], query_flags, url_lower[i]),
                i,
            )
            for i, blob in enumerate(blobs)
        )

        # В рабочем режиме top_k обычно равен 1 или 5. Генератор не хранит
        # scores для всего индекса, а nlargest держит только top_k результатов.
        best = nlargest(limit, scored, key=lambda item: (item[0], -item[1]))
        result = [(docs[i], score) for score, i in best]

        with self._lock:
            # Обновление индекса могло произойти, пока считались fuzzy scores.
            # Не возвращаем устаревший snapshot в кэш после такого обновления.
            if version == self._version:
                cached = self._search_cache.get(cache_key)
                if cached is None or len(result) >= len(cached):
                    self._search_cache[cache_key] = result
                self._search_cache.move_to_end(cache_key)
                if len(self._search_cache) > _SEARCH_CACHE_SIZE:
                    self._search_cache.popitem(last=False)

        return list(result)



    def add_docs(self, new_docs: list[WebWikiDoc]) -> None:

        if not new_docs:

            return

        # Подготовка blobs/token sets не зависит от состояния индекса и не
        # должна блокировать поиск на время CPU-операций.
        new_docs_tuple = tuple(new_docs)
        new_blobs = tuple(_make_search_blob(d) for d in new_docs_tuple)
        new_url_lower = tuple((d.url or "").lower() for d in new_docs_tuple)
        new_blob_tokens = tuple(frozenset(blob.split()) for blob in new_blobs)
        new_error_code_docs = _build_error_code_docs(new_docs_tuple)

        with self._lock:

            self._docs = (*self._docs, *new_docs_tuple)
            self._blobs = (*self._blobs, *new_blobs)
            self._url_lower = (*self._url_lower, *new_url_lower)
            self._blob_tokens = (*self._blob_tokens, *new_blob_tokens)
            for code, docs in new_error_code_docs.items():
                self._error_code_docs.setdefault(code, []).extend(docs)

            self._version += 1
            self._search_cache.clear()

    def replace_docs(self, docs: list[WebWikiDoc]) -> None:
        docs_tuple = tuple(docs)
        blobs = tuple(_make_search_blob(d) for d in docs_tuple)
        url_lower = tuple((d.url or "").lower() for d in docs_tuple)
        blob_tokens = tuple(frozenset(blob.split()) for blob in blobs)
        error_code_docs = _build_error_code_docs(docs_tuple)

        with self._lock:
            self._docs = docs_tuple
            self._blobs = blobs
            self._url_lower = url_lower
            self._blob_tokens = blob_tokens
            self._error_code_docs = error_code_docs
            self._version += 1
            self._search_cache.clear()

    def upsert_docs(self, updated_docs: list[WebWikiDoc]) -> None:
        """Заменяет совпавшие URL и добавляет новые без промежуточной пустой базы."""
        if not updated_docs:
            return

        while True:
            with self._lock:
                version = self._version
                by_url = {doc.url: doc for doc in self._docs}

            for doc in updated_docs:
                by_url[doc.url] = doc
            docs = tuple(by_url.values())
            blobs = tuple(_make_search_blob(doc) for doc in docs)
            url_lower = tuple((doc.url or "").lower() for doc in docs)
            blob_tokens = tuple(frozenset(blob.split()) for blob in blobs)
            error_code_docs = _build_error_code_docs(docs)

            with self._lock:
                if version != self._version:
                    continue
                self._docs = docs
                self._blobs = blobs
                self._url_lower = url_lower
                self._blob_tokens = blob_tokens
                self._error_code_docs = error_code_docs
                self._version += 1
                self._search_cache.clear()
                return





@dataclass(slots=True)

class WikiState:

    sitemap_url: str

    base_url: str

    max_pages: int

    urls: list[str]

    next_idx: int = 0

    done_notified: bool = False

    cache_version: int = 0

    page_meta: dict[str, dict[str, object]] = field(default_factory=dict)

    status: str = "queued"

    source: str = "seed"

    cycle_started_at: float | None = None

    cycle_completed_at: float | None = None

    next_cycle_at: float = 0.0

    limited: bool = False

    dropped_urls: int = 0

    last_error: str | None = None

    last_request_at: float = 0.0

    robots_txt: str | None = None

    robots_fetched_at: float = 0.0

    robots_retry_at: float = 0.0


def _safe_nonnegative_int(value: object, default: int) -> int:
    """Читает целое из state-файла без отрицательных и boolean-значений."""
    if isinstance(value, bool):
        return default
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if result >= 0 else default





class WebWikiIndexer:

    """

    Постепенно обходит статьи и сохраняет документы с очередью в checkpoint.

    """



    def __init__(

        self,

        *,

        index: WebWikiIndex,

        cache_path: str,

        state_path: str,

        sitemap_url: str,

        base_url: str,

        max_pages: int,

        extra_urls: tuple[str, ...] = (),

        refresh_hours: int = 24,

    ) -> None:

        self.index = index

        self.cache_file = Path(cache_path)

        self.state_file = Path(state_path)

        self.sitemap_url = sitemap_url

        self.base_url = base_url

        self.max_pages = max_pages

        self.extra_urls = tuple(dict.fromkeys(_DEFAULT_EXTRA_WIKI_URLS + tuple(extra_urls)))

        self.refresh_hours = max(1, int(refresh_hours))

        self._crawler_lock = threading.Lock()

        self._docs_by_url: dict[str, WebWikiDoc] = {}

        self._checkpoint_is_current = False

        self._legacy_docs: list[WebWikiDoc] = []



        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        self.state_file.parent.mkdir(parents=True, exist_ok=True)



        self._state = self._load_or_init_state()



    def _new_seed_state(self) -> WikiState:
        home = urljoin(self.base_url + "/", "/en/home")
        candidates = _dedupe_urls(
            [*self.extra_urls, *_read_sitemap_snapshot_urls(self.base_url, 0)],
            base_url=self.base_url,
            max_pages=0,
        )
        ordered = [home] + sorted(
            (url for url in candidates if url != home),
            key=_crawl_priority,
        )
        all_urls = _dedupe_urls(ordered, base_url=self.base_url, max_pages=0)
        urls = _dedupe_urls(all_urls, base_url=self.base_url, max_pages=self.max_pages)
        dropped = max(0, len(all_urls) - len(urls))
        return WikiState(
            sitemap_url=self.sitemap_url,
            base_url=self.base_url,
            max_pages=self.max_pages,
            urls=urls,
            limited=dropped > 0,
            dropped_urls=dropped,
        )

    def _load_or_init_state(self) -> WikiState:
        raw: object = None
        try:
            if self.cache_file.stat().st_size > _MAX_INDEX_CACHE_BYTES:
                raise ValueError("wiki cache exceeds configured size limit")
            raw = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, json.JSONDecodeError):
            logging.warning("Wiki checkpoint не удалось прочитать; исходный файл сохранён")

        if isinstance(raw, dict) and raw.get("format") == _CHECKPOINT_FORMAT:
            if raw.get("version") == _CHECKPOINT_VERSION:
                docs = _docs_from_payload(raw.get("documents"))
                self._docs_by_url = {doc.url: doc for doc in docs}
                self._legacy_docs = docs
                state = raw.get("state")
                if isinstance(state, dict):
                    self._checkpoint_is_current = True
                    loaded_state = _state_from_payload(
                        state,
                        sitemap_url=self.sitemap_url,
                        base_url=self.base_url,
                        max_pages=self.max_pages,
                    )
                    valid_queue = _dedupe_urls(
                        loaded_state.urls, base_url=self.base_url, max_pages=0
                    )
                    loaded_state.urls = _dedupe_urls(
                        valid_queue,
                        base_url=self.base_url,
                        max_pages=self.max_pages,
                    )
                    if len(loaded_state.urls) < len(valid_queue):
                        loaded_state.limited = True
                        loaded_state.dropped_urls += len(valid_queue) - len(loaded_state.urls)
                    return loaded_state
            logging.warning("Wiki checkpoint имеет неподдерживаемый формат; старый файл сохранён")
            backup = self.cache_file.with_name(self.cache_file.name + ".legacy")
            self._legacy_docs = _load_cache(backup)
            self._docs_by_url = {doc.url: doc for doc in self._legacy_docs}
            state = self._new_seed_state()
            merged_urls = _dedupe_urls(
                list(self._docs_by_url) + state.urls,
                base_url=self.base_url,
                max_pages=0,
            )
            state.urls = _dedupe_urls(merged_urls, base_url=self.base_url, max_pages=self.max_pages)
            if len(state.urls) < len(merged_urls):
                state.limited = True
                state.dropped_urls += len(merged_urls) - len(state.urls)
            state.last_error = "unsupported or damaged checkpoint; using preserved cache"
            return state

        if isinstance(raw, list):
            docs = _load_cache(self.cache_file)
        else:
            legacy_backup = self.cache_file.with_name(self.cache_file.name + ".legacy")
            docs = _load_cache(legacy_backup)
        self._docs_by_url = {doc.url: doc for doc in docs}
        self._legacy_docs = docs
        state = self._new_seed_state()
        legacy_urls: list[str] = []
        try:
            legacy = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(legacy, dict) and isinstance(legacy.get("urls"), list):
                old_urls = [url for url in legacy["urls"] if isinstance(url, str)]
                old_next = _safe_nonnegative_int(legacy.get("next_idx"), 0)
                legacy_urls = old_urls[min(old_next, len(old_urls)) :]
        except (OSError, json.JSONDecodeError):
            pass
        merged_urls = _dedupe_urls(
            legacy_urls + list(self._docs_by_url) + state.urls,
            base_url=self.base_url,
            max_pages=0,
        )
        state.urls = _dedupe_urls(merged_urls, base_url=self.base_url, max_pages=self.max_pages)
        if len(state.urls) < len(merged_urls):
            state.limited = True
            state.dropped_urls += len(merged_urls) - len(state.urls)
        state.source = "legacy-and-seed" if legacy_urls or docs else "seed"
        return state

    def _checkpoint_payload(
        self, state: WikiState, docs: dict[str, WebWikiDoc]
    ) -> dict[str, object]:
        return {
            "format": _CHECKPOINT_FORMAT,
            "version": _CHECKPOINT_VERSION,
            "documents": [
                {"title": doc.title, "url": doc.url, "text": doc.text}
                for doc in docs.values()
            ],
            "state": _state_to_payload(state),
        }

    def _persist_checkpoint(
        self, state: WikiState, docs: dict[str, WebWikiDoc]
    ) -> None:
        encoded = json.dumps(self._checkpoint_payload(state, docs), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > _MAX_INDEX_CACHE_BYTES:
            raise ValueError("wiki checkpoint превышает допустимый размер")
        if not self._checkpoint_is_current:
            for legacy_path in (self.cache_file, self.state_file):
                if legacy_path.is_file():
                    backup = legacy_path.with_name(legacy_path.name + ".legacy")
                    if not backup.exists():
                        shutil.copy2(legacy_path, backup)
        _atomic_write_text(self.cache_file, encoded)
        persisted = json.loads(self.cache_file.read_text(encoding="utf-8"))
        expected = json.loads(encoded)
        if (
            persisted != expected
            or not isinstance(persisted, dict)
            or persisted.get("format") != _CHECKPOINT_FORMAT
            or persisted.get("version") != _CHECKPOINT_VERSION
            or not isinstance(persisted.get("documents"), list)
            or not isinstance(persisted.get("state"), dict)
        ):
            raise ValueError("wiki checkpoint read-back validation failed")
        self._checkpoint_is_current = True

    def _save_state(self, st: WikiState | None = None) -> None:
        state = st or self._state
        self._persist_checkpoint(state, self._docs_by_url)
        self._state = state

    def load_cached_docs(self) -> None:
        self.index.replace_docs(self._legacy_docs)
        if self._legacy_docs:
            logging.info("Загружен кэш индекса: %d страниц", len(self._legacy_docs))

    def is_done(self) -> bool:
        return not self._state.urls and self._state.next_cycle_at > time.time()

    def is_done_notified(self) -> bool:

        return bool(self._state.done_notified)



    def mark_done_notified(self) -> None:

        self._state.done_notified = True

        self._save_state(self._state)



    def step(self, batch_size: int) -> int:
        if not self._crawler_lock.acquire(blocking=False):
            return 0
        try:
            now = time.time()
            state = copy.deepcopy(self._state)
            docs = dict(self._docs_by_url)
            if not state.urls and state.next_cycle_at <= now:
                previous_meta = state.page_meta
                state = self._new_seed_state()
                state.page_meta = copy.deepcopy(previous_meta)
                unbounded_queue = _dedupe_urls(
                    list(docs) + state.urls,
                    base_url=self.base_url,
                    max_pages=0,
                )
                state.urls = _dedupe_urls(
                    unbounded_queue, base_url=self.base_url, max_pages=self.max_pages
                )
                if len(state.urls) < len(unbounded_queue):
                    state.limited = True
                    state.dropped_urls += len(unbounded_queue) - len(state.urls)
                state.cycle_started_at = now
                state.next_cycle_at = now + self.refresh_hours * 3600
                state.status = "running"
                state.source = "scheduled-refresh"
            if not state.urls:
                return 0

            state.status = "running"
            state.cycle_started_at = state.cycle_started_at or now
            changed_docs: list[WebWikiDoc] = []
            processed = 0
            client = httpx.Client(
                timeout=httpx.Timeout(20.0, connect=10.0),
                follow_redirects=False,
                headers={"User-Agent": _WIKI_USER_AGENT},
            )
            try:
                if not _refresh_robots_policy(client, state, self.base_url, now):
                    state.status = "waiting-robots"
                    self._persist_checkpoint(state, docs)
                    self._state = state
                    return 0

                while processed < max(1, batch_size):
                    due_index = _find_due_url(state.urls, state.page_meta, time.time())
                    if due_index is None:
                        break
                    url = state.urls.pop(due_index)
                    meta = state.page_meta.setdefault(url, {})
                    if not _robots_allows(state.robots_txt, url):
                        meta.update(last_error="blocked by robots.txt", next_retry_at=0.0)
                        processed += 1
                        continue

                    delay = max(
                        _MIN_WIKI_REQUEST_INTERVAL_SECONDS,
                        _robots_crawl_delay(state.robots_txt),
                    ) - (time.time() - state.last_request_at)
                    if state.last_request_at and delay > 0:
                        time.sleep(delay)

                    validators: dict[str, str] = {}
                    if meta.get("etag"):
                        validators["If-None-Match"] = str(meta["etag"])
                    if meta.get("last_modified"):
                        validators["If-Modified-Since"] = str(meta["last_modified"])
                    state.last_request_at = time.time()
                    try:
                        response = _safe_http_get(
                            client, url, base_url=self.base_url,
                            max_bytes=_MAX_WIKI_PAGE_BYTES, headers=validators,
                        )
                        if response.status_code == 304 and url in docs:
                            meta.update(
                                last_checked_at=time.time(),
                                last_success_at=time.time(),
                                last_error=None,
                                attempts=0,
                                next_retry_at=0.0,
                            )
                        elif response.status_code == 304:
                            response = _safe_http_get(
                                client, url, base_url=self.base_url,
                                max_bytes=_MAX_WIKI_PAGE_BYTES, headers={},
                            )
                            self._process_page_response(
                                url, response, state, docs, changed_docs
                            )
                        else:
                            self._process_page_response(
                                url, response, state, docs, changed_docs
                            )
                    except Exception as exc:
                        self._record_page_failure(url, meta, str(exc), time.time(), state=state)
                    processed += 1

                if not state.urls:
                    state.status = "limited" if state.limited else "complete"
                    state.cycle_completed_at = time.time()
                    state.next_cycle_at = state.cycle_completed_at + self.refresh_hours * 3600
                    state.done_notified = False
                elif _find_due_url(state.urls, state.page_meta, time.time()) is None:
                    state.status = "waiting-retry"

                self._persist_checkpoint(state, docs)
                if changed_docs:
                    self.index.upsert_docs(changed_docs)
                self._state = state
                self._docs_by_url = docs
                logging.info(
                    "Индексация вики: status=%s queue=%d docs=%d updated=%d",
                    state.status, len(state.urls), len(docs), len(changed_docs),
                )
                return len(changed_docs)
            finally:
                client.close()
        finally:
            self._crawler_lock.release()

    def _process_page_response(
        self,
        url: str,
        response: WikiHttpResponse,
        state: WikiState,
        docs: dict[str, WebWikiDoc],
        changed_docs: list[WebWikiDoc],
    ) -> None:
        meta = state.page_meta.setdefault(url, {})
        if response.status_code != 200:
            if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
                retry_after = (
                    _parse_retry_after(response.headers["retry-after"])
                    if response.status_code == 429 and response.headers.get("retry-after")
                    else 0.0
                )
                self._record_page_failure(
                    url, meta, f"HTTP {response.status_code}", time.time(),
                    retry_after=retry_after,
                    state=state,
                )
            else:
                meta.update(
                    last_error=f"HTTP {response.status_code}",
                    last_checked_at=time.time(),
                    next_retry_at=0.0,
                )
            return

        content_type = response.headers.get("content-type", "text/html").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            meta.update(
                last_error=f"non-HTML content: {content_type}",
                last_checked_at=time.time(),
                next_retry_at=0.0,
            )
            return

        html_text = response.content.decode("utf-8", errors="replace")
        title, text, links = _extract_page_from_html(html_text, response.url, self.base_url)
        if _looks_like_error_page(title, text):
            self._record_page_failure(url, meta, "error or challenge page", time.time(), state=state)
            return

        doc = WebWikiDoc(title=title, url=url, text=text)
        if docs.get(url) != doc:
            docs[url] = doc
            changed_docs.append(doc)
        meta.update(
            links=links,
            text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            links_hash=hashlib.sha256("\n".join(links).encode("utf-8")).hexdigest(),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
            last_checked_at=time.time(),
            last_success_at=time.time(),
            last_error=None,
            attempts=0,
            next_retry_at=0.0,
        )
        state.last_error = None
        self._enqueue_discovered(links, state, docs)

    def _enqueue_discovered(
        self, links: list[str], state: WikiState, docs: dict[str, WebWikiDoc]
    ) -> None:
        known = set(state.urls) | set(docs)
        for link in sorted((item for item in links if item not in known), key=_crawl_priority):
            if len(state.urls) >= _MAX_WIKI_QUEUE_URLS:
                state.limited = True
                state.dropped_urls += 1
                continue
            if self.max_pages > 0 and len(known) >= self.max_pages:
                state.limited = True
                state.dropped_urls += 1
                continue
            state.urls.append(link)
            known.add(link)

    def _record_page_failure(
        self,
        url: str,
        meta: dict[str, object],
        error: str,
        now: float,
        *,
        retry_after: float = 0.0,
        state: WikiState | None = None,
    ) -> None:
        attempts = _safe_nonnegative_int(meta.get("attempts"), 0) + 1
        delay = max(
            retry_after,
            min(86400.0, 60.0 * (2 ** min(attempts - 1, 10))),
        )
        delay += random.uniform(0.0, min(30.0, delay * 0.1))
        meta.update(
            last_error=error,
            attempts=attempts,
            next_retry_at=now + delay,
            last_checked_at=now,
        )
        if state is not None:
            state.last_error = error
            if url not in state.urls:
                state.urls.append(url)

    def request_refresh(
        self, urls: list[str] | None = None, *, source: str = "manual"
    ) -> bool:
        """Ставит обновление в общую очередь, не очищая текущий индекс."""
        if not self._crawler_lock.acquire(blocking=False):
            return False
        try:
            state = copy.deepcopy(self._state)
            docs = dict(self._docs_by_url)
            candidates = urls or list(docs) or self._new_seed_state().urls
            state.urls = _dedupe_urls(
                state.urls + candidates,
                base_url=self.base_url,
                max_pages=self.max_pages,
            )
            for url in state.urls:
                state.page_meta.setdefault(url, {})["next_retry_at"] = 0.0
            state.next_idx = 0
            state.status = "queued"
            state.source = source
            state.cycle_started_at = None
            state.limited = False
            state.dropped_urls = 0
            self._persist_checkpoint(state, docs)
            self._state = state
            return True
        finally:
            self._crawler_lock.release()

    def enqueue_urls(self, urls: list[str], *, source: str = "sitemap") -> int:
        with self._crawler_lock:
            state = copy.deepcopy(self._state)
            docs = dict(self._docs_by_url)
            known = set(state.urls)
            added = 0
            for url in sorted(
                _dedupe_urls(urls, base_url=self.base_url), key=_crawl_priority
            ):
                if url in known:
                    continue
                if (
                    self.max_pages > 0
                    and url not in docs
                    and len(set(docs) | known) >= self.max_pages
                ):
                    state.limited = True
                    state.dropped_urls += 1
                    continue
                state.urls.append(url)
                known.add(url)
                added += 1
            if added:
                state.status = "queued"
                state.source = source
                self._persist_checkpoint(state, docs)
                self._state = state
            return added

    def status_snapshot(self) -> dict[str, object]:
        state = self._state
        now = time.time()
        page_errors = [meta for meta in state.page_meta.values() if meta.get("last_error")]
        delayed = sum(
            1 for meta in page_errors
            if (_safe_timestamp(meta.get("next_retry_at")) or 0.0) > now
        )
        return {
            "status": state.status,
            "documents": len(self._docs_by_url),
            "queued": len(state.urls),
            "delayed_errors": delayed,
            "errors": len(page_errors),
            "last_success_at": max(
                (
                    _safe_timestamp(meta.get("last_success_at")) or 0.0
                    for meta in state.page_meta.values()
                ),
                default=0.0,
            ),
            "cycle_started_at": state.cycle_started_at,
            "cycle_completed_at": state.cycle_completed_at,
            "next_cycle_at": state.next_cycle_at,
            "source": state.source,
            "limited": state.limited,
            "dropped_urls": state.dropped_urls,
            "last_error": state.last_error,
        }

    def index_snapshot(self) -> list[WebWikiDoc]:

        # берём срез безопасно через поиск-лок

        with self.index._lock:  # noqa: SLF001 (внутреннее использование)

            return list(self.index._docs)





@dataclass(frozen=True, slots=True)
class WikiHttpResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str


def _state_to_payload(state: WikiState) -> dict[str, object]:
    return {
        "sitemap_url": state.sitemap_url,
        "base_url": state.base_url,
        "max_pages": state.max_pages,
        "urls": state.urls,
        "next_idx": state.next_idx,
        "done_notified": state.done_notified,
        "cache_version": state.cache_version,
        "page_meta": state.page_meta,
        "status": state.status,
        "source": state.source,
        "cycle_started_at": state.cycle_started_at,
        "cycle_completed_at": state.cycle_completed_at,
        "next_cycle_at": state.next_cycle_at,
        "limited": state.limited,
        "dropped_urls": state.dropped_urls,
        "last_error": state.last_error,
        "last_request_at": state.last_request_at,
        "robots_txt": state.robots_txt,
        "robots_fetched_at": state.robots_fetched_at,
        "robots_retry_at": state.robots_retry_at,
    }


def _state_from_payload(
    raw: dict[str, object], *, sitemap_url: str, base_url: str, max_pages: int
) -> WikiState:
    urls = raw.get("urls")
    raw_meta = raw.get("page_meta")
    page_meta = (
        {
            key: value
            for key, value in raw_meta.items()
            if isinstance(key, str) and isinstance(value, dict)
        }
        if isinstance(raw_meta, dict)
        else {}
    )
    return WikiState(
        sitemap_url=sitemap_url,
        base_url=base_url,
        max_pages=max_pages,
        urls=[url for url in urls if isinstance(url, str)] if isinstance(urls, list) else [],
        next_idx=_safe_nonnegative_int(raw.get("next_idx"), 0),
        done_notified=raw.get("done_notified") is True,
        cache_version=_INDEX_CACHE_VERSION,
        page_meta=page_meta,
        status=str(raw.get("status") or "queued"),
        source=str(raw.get("source") or "checkpoint"),
        cycle_started_at=_safe_timestamp(raw.get("cycle_started_at")),
        cycle_completed_at=_safe_timestamp(raw.get("cycle_completed_at")),
        next_cycle_at=_safe_timestamp(raw.get("next_cycle_at")) or 0.0,
        limited=raw.get("limited") is True,
        dropped_urls=_safe_nonnegative_int(raw.get("dropped_urls"), 0),
        last_error=raw.get("last_error") if isinstance(raw.get("last_error"), str) else None,
        last_request_at=_safe_timestamp(raw.get("last_request_at")) or 0.0,
        robots_txt=raw.get("robots_txt") if isinstance(raw.get("robots_txt"), str) else None,
        robots_fetched_at=_safe_timestamp(raw.get("robots_fetched_at")) or 0.0,
        robots_retry_at=_safe_timestamp(raw.get("robots_retry_at")) or 0.0,
    )


def _safe_timestamp(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 and result < float("inf") else None


def _docs_from_payload(raw: object) -> list[WebWikiDoc]:
    if not isinstance(raw, list):
        return []
    by_url: dict[str, WebWikiDoc] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Wiki").strip() or "Wiki"
        url = str(item.get("url") or "").strip()
        text = str(item.get("text") or "").strip()
        if url and text:
            by_url[url] = WebWikiDoc(title=title, url=url, text=text)
    return list(by_url.values())


def _find_due_url(
    urls: list[str], page_meta: dict[str, dict[str, object]], now: float
) -> int | None:
    for index, url in enumerate(urls):
        if float(page_meta.get(url, {}).get("next_retry_at", 0) or 0) <= now:
            return index
    return None


def _crawl_priority(url: str) -> tuple[int, str]:
    normalized = url.lower()
    if "kobra-s1" in normalized:
        return (0, normalized)
    if normalized.endswith("/en/home"):
        return (1, normalized)
    return (2, normalized)


def _url_is_same_origin(url: str, base_url: str) -> bool:
    try:
        target = urlsplit(url)
        base = urlsplit(base_url)
        return (
            target.scheme.lower() == "https"
            and target.hostname is not None
            and target.hostname.lower() == (base.hostname or "").lower()
            and target.port == base.port
            and not target.username
            and not target.password
        )
    except ValueError:
        return False


def _normalize_wiki_url(
    raw_url: str,
    *,
    base_url: str,
    source_url: str | None = None,
    allow_non_article_path: bool = False,
) -> str | None:
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None
    candidate = urljoin(source_url or (base_url.rstrip("/") + "/"), raw_url.strip())
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if not _url_is_same_origin(candidate, base_url):
        return None
    path = parsed.path or "/"
    if not allow_non_article_path and path != "/en" and not path.startswith("/en/"):
        return None
    return urlunsplit(("https", parsed.netloc.lower(), path, "", ""))


def _safe_http_get(
    client: httpx.Client,
    url: str,
    *,
    base_url: str,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    allow_non_article_path: bool = False,
) -> WikiHttpResponse:
    current = _normalize_wiki_url(
        url, base_url=base_url, allow_non_article_path=allow_non_article_path
    )
    if current is None:
        raise ValueError("URL не входит в разрешённый origin/path")
    for redirect_count in range(_MAX_REDIRECTS + 1):
        with client.stream(
            "GET", current, headers=headers or {}, follow_redirects=False
        ) as response:
            response_headers = {
                key.lower(): value for key, value in response.headers.items()
            }
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response_headers.get("location")
                if not location or redirect_count >= _MAX_REDIRECTS:
                    raise ValueError("недопустимый или слишком длинный redirect")
                target = _normalize_wiki_url(
                    location,
                    base_url=base_url,
                    source_url=current,
                    allow_non_article_path=allow_non_article_path,
                )
                if target is None:
                    raise ValueError("redirect покидает разрешённый origin/path")
                current = target
                continue
            if response.status_code == 304:
                return WikiHttpResponse(304, response_headers, b"", current)
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError("ответ превышает допустимый размер")
            return WikiHttpResponse(
                response.status_code, response_headers, bytes(content), current
            )
    raise ValueError("превышен лимит redirect")


def _refresh_robots_policy(
    client: httpx.Client, state: WikiState, base_url: str, now: float
) -> bool:
    if state.robots_txt is not None and now - state.robots_fetched_at < 86400:
        return True
    if state.robots_retry_at > now:
        return False
    try:
        response = _safe_http_get(
            client,
            base_url.rstrip("/") + "/robots.txt",
            base_url=base_url,
            max_bytes=512 * 1024,
            allow_non_article_path=True,
        )
        if response.status_code in {404, 410}:
            state.robots_txt = ""
        elif response.status_code in {401, 403}:
            state.robots_txt = "User-agent: *\nDisallow: /"
        elif response.status_code == 200:
            state.robots_txt = response.content.decode("utf-8", errors="replace")
        else:
            state.robots_retry_at = now + 300
            state.last_error = f"robots.txt HTTP {response.status_code}"
            return False
        state.robots_fetched_at = now
        state.robots_retry_at = 0.0
        return True
    except Exception as exc:
        state.robots_retry_at = now + 300
        state.last_error = f"robots.txt: {exc}"
        return False


def _robots_allows(robots_txt: str | None, url: str) -> bool:
    if robots_txt is None:
        return False
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    return parser.can_fetch(_WIKI_USER_AGENT, url)


def _robots_crawl_delay(robots_txt: str | None) -> float:
    if not robots_txt:
        return 0.0
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    try:
        return max(0.0, float(parser.crawl_delay(_WIKI_USER_AGENT) or 0))
    except (TypeError, ValueError):
        return 0.0


def _parse_retry_after(value: str) -> float:
    try:
        return max(0.0, float(value))
    except ValueError:
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime
        try:
            target = parsedate_to_datetime(value)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0


def _read_sitemap_snapshot_urls(base_url: str, max_pages: int) -> list[str]:
    path = Path(__file__).resolve().parent.parent / "data" / "sitemap.xml"
    if not path.is_file():
        return []
    try:
        return _parse_sitemap_urls(
            path.read_text(encoding="utf-8"),
            base_url=base_url,
            max_pages=max_pages,
        )
    except (OSError, ValueError, ET.ParseError) as exc:
        logging.warning("Локальный sitemap недоступен или некорректен: %s", exc)
        return []


def _parse_sitemap_urls(
    content: str, *, base_url: str, max_pages: int
) -> list[str]:
    if len(content.encode("utf-8")) > _MAX_SITEMAP_BYTES:
        raise ValueError("ответ sitemap превышает допустимый размер")
    root = ET.fromstring(content)
    if not root.tag.endswith(("urlset", "sitemapindex")):
        raise ValueError("ответ sitemap не является XML-картой сайта")
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [
        loc.text.strip()
        for loc in root.findall(".//sm:url/sm:loc", ns)
        if loc.text and loc.text.strip()
    ]
    return _dedupe_urls(urls, base_url=base_url, max_pages=max_pages)


def _dedupe_urls(urls: list[str], *, base_url: str, max_pages: int = 0) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    limit = min(max_pages, _MAX_WIKI_QUEUE_URLS) if max_pages > 0 else _MAX_WIKI_QUEUE_URLS
    for raw_url in urls:
        url = _normalize_wiki_url(raw_url, base_url=base_url)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)
        if len(result) >= limit:
            break
    return result


def _read_sitemap_urls(
    sitemap_url: str,
    *,
    max_pages: int,
    base_url: str,
    extra_urls: tuple[str, ...] = (),
) -> list[str]:
    discovered: list[str] = []
    if sitemap_url.strip():
        try:
            with httpx.Client(
                timeout=20.0,
                follow_redirects=False,
                headers={"User-Agent": _WIKI_USER_AGENT},
            ) as client:
                response = _safe_http_get(
                    client,
                    sitemap_url,
                    base_url=base_url,
                    max_bytes=_MAX_SITEMAP_BYTES,
                    allow_non_article_path=True,
                )
            if response.status_code != 200:
                raise ValueError(f"sitemap HTTP {response.status_code}")
            discovered = _parse_sitemap_urls(
                response.content.decode("utf-8", errors="replace"),
                base_url=base_url,
                max_pages=max_pages,
            )
        except Exception as exc:
            logging.warning("Sitemap недоступен или некорректен; использую локальный список: %s", exc)
    if not discovered:
        discovered = _read_sitemap_snapshot_urls(base_url, max_pages)
    return _dedupe_urls(
        list(extra_urls) + discovered,
        base_url=base_url,
        max_pages=max_pages,
    )


def _extract_page_from_html(
    html: str, source_url: str, base_url: str
) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.get_text(strip=True) if soup.title else "").strip()
    links = _dedupe_urls(
        [
            urljoin(source_url, anchor.get("href", ""))
            for anchor in soup.find_all("a", href=True)
        ],
        base_url=base_url,
    )
    content = soup.find("template", attrs={"slot": "contents"})
    text_source = content if content is not None else (soup.body or soup)
    for tag in text_source(["script", "style", "noscript"]):
        tag.decompose()
    text = _normalize(f"{title}\n{text_source.get_text(' ', strip=True)}")
    return title or "Wiki", text, links


def _looks_like_error_page(title: str, text: str) -> bool:
    if not text.strip():
        return True
    title_lower = title.lower()
    if any(marker in title_lower for marker in (
        "page not found", "404", "access denied", "forbidden", "captcha"
    )):
        return True
    if len(text) < 120 and any(marker in text.lower() for marker in (
        "verify you are human", "checking your browser", "access denied", "captcha"
    )):
        return True
    return False


def _extract_text_from_html(html: str) -> tuple[str, str]:

    soup = BeautifulSoup(html, "html.parser")

    title = (soup.title.get_text(strip=True) if soup.title else "").strip()



    content = soup.find("template", attrs={"slot": "contents"})

    source = content if content is not None else (soup.body or soup)

    for tag in source(["script", "style", "noscript"]):

        tag.decompose()



    body = source.get_text(" ", strip=True)

    text = _normalize(f"{title}\n{body}")

    return title or "Wiki", text





def _fetch_docs(urls: list[str]) -> list[WebWikiDoc]:
    docs: list[WebWikiDoc] = []
    with httpx.Client(
        timeout=20.0,
        follow_redirects=False,
        headers={"User-Agent": _WIKI_USER_AGENT},
    ) as client:
        for url in urls:
            try:
                response = _safe_http_get(
                    client,
                    url,
                    base_url=url,
                    max_bytes=_MAX_WIKI_PAGE_BYTES,
                )
                if response.status_code != 200:
                    continue
                content_type = response.headers.get("content-type", "text/html").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    continue
                title, text = _extract_text_from_html(
                    response.content.decode("utf-8", errors="replace")
                )
                if not _looks_like_error_page(title, text):
                    docs.append(WebWikiDoc(title=title, url=url, text=text))
            except Exception:
                continue
    if not docs:
        raise RuntimeError("Не получилось скачать страницы вики для индекса")
    return docs


def _save_cache(path: Path, docs: list[WebWikiDoc]) -> None:

    payload = [{"title": d.title, "url": d.url, "text": d.text} for d in docs]

    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False))


_ATOMIC_REPLACE_LOCK = threading.Lock()
_ATOMIC_REPLACE_RETRIES = 5


def _atomic_write_text(path: Path, content: str) -> None:
    """Атомарно заменяет файл; Windows PermissionError повторяется ограниченно."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        with _ATOMIC_REPLACE_LOCK:
            for attempt in range(_ATOMIC_REPLACE_RETRIES):
                try:
                    Path(temporary_name).replace(path)
                    break
                except PermissionError:
                    if os.name != "nt" or attempt == _ATOMIC_REPLACE_RETRIES - 1:
                        raise
                    time.sleep(0.01 * (2 ** attempt))
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _load_cache(path: Path) -> list[WebWikiDoc]:

    try:

        cache_size = path.stat().st_size
        if cache_size > _MAX_INDEX_CACHE_BYTES:
            logging.warning(
                "Кэш индекса слишком большой и будет перестроен: %s (байт: %d)",
                path.as_posix(),
                cache_size,
            )
            return []

        raw = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(raw, list):
            return []

        by_url: dict[str, WebWikiDoc] = {}

        for item in raw:

            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip() or "Wiki"

            url = str(item.get("url") or "").strip()

            text = str(item.get("text") or "").strip()

            if url and text:

                doc = WebWikiDoc(title=title, url=url, text=text)

                previous = by_url.get(url)

                if previous is None or len(doc.text) > len(previous.text):

                    by_url[url] = doc

        return list(by_url.values())

    except Exception:

        return []
