from __future__ import annotations



import json
import tempfile

import re
import xml.etree.ElementTree as ET

from collections import OrderedDict
from dataclasses import dataclass
from heapq import nlargest

from pathlib import Path

from urllib.parse import urlparse



import httpx

from bs4 import BeautifulSoup

from rapidfuzz import fuzz

import logging

import threading





from app.bot.text_heuristics import (
    _is_marketplace_promo_message,
    _is_non_wiki_chatter_message,
)



def _normalize(text: str) -> str:

    return " ".join(text.lower().split())





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





def _looks_like_question(text: str) -> bool:

    if _is_marketplace_promo_message(text):

        return False

    if _is_non_wiki_chatter_message(text):

        return False

    t = _normalize(text)

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
_MAX_INDEX_CACHE_BYTES = 64 * 1024 * 1024
_MAX_SITEMAP_BYTES = 16 * 1024 * 1024
_MAX_WIKI_PAGE_BYTES = 16 * 1024 * 1024
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

        overlap = len(q_tokens & b_tokens)

        bonus = min(26, overlap * 5)



        if is_replacement_query:

            if "replacement" in doc.url or "replace" in doc.url or "install" in doc.url:

                bonus += 10



        if is_component_query:

            if "/faq" in doc.url or doc.url.rstrip("/").endswith("/faq"):

                bonus -= 14



        if has_kobra and "kobra" in blob:

            bonus += 8

        if "s1" in q_tokens and "s1" in b_tokens:

            bonus += 8

        if "combo" in q_tokens and "combo" in b_tokens:

            bonus += 8



        return max(0, min(100, base + bonus))



    def search(self, query: str, *, top_k: int = 1) -> list[tuple[WebWikiDoc, int]]:

        q = _normalize(query)
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
                self._score_one(q, docs[i], blob, q_tokens, blob_tokens[i], query_flags),
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

        with self._lock:

            new_blobs = [_make_search_blob(d) for d in new_docs]
            self._docs = (*self._docs, *new_docs)
            self._blobs = (*self._blobs, *new_blobs)
            self._blob_tokens = (*self._blob_tokens, *(frozenset(blob.split()) for blob in new_blobs))
            for code, docs in _build_error_code_docs(tuple(new_docs)).items():
                self._error_code_docs.setdefault(code, []).extend(docs)

            self._version += 1
            self._search_cache.clear()

    def replace_docs(self, docs: list[WebWikiDoc]) -> None:
        with self._lock:
            self._docs = tuple(docs)
            self._blobs = tuple(_make_search_blob(d) for d in self._docs)
            self._blob_tokens = tuple(frozenset(blob.split()) for blob in self._blobs)
            self._error_code_docs = _build_error_code_docs(self._docs)
            self._version += 1
            self._search_cache.clear()





@dataclass(slots=True)

class WikiState:

    sitemap_url: str

    base_url: str

    max_pages: int

    urls: list[str]

    next_idx: int

    done_notified: bool = False

    cache_version: int = 0


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

    Постепенно индексирует страницы по sitemap, сохраняя прогресс на диск.

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

    ) -> None:

        self.index = index

        self.cache_file = Path(cache_path)

        self.state_file = Path(state_path)

        self.sitemap_url = sitemap_url

        self.base_url = base_url

        self.max_pages = max_pages

        self.extra_urls = tuple(dict.fromkeys(_DEFAULT_EXTRA_WIKI_URLS + tuple(extra_urls)))



        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        self.state_file.parent.mkdir(parents=True, exist_ok=True)



        self._state = self._load_or_init_state()



    def _load_or_init_state(self) -> WikiState:

        if self.state_file.exists():

            try:

                raw = json.loads(self.state_file.read_text(encoding="utf-8"))

                if not isinstance(raw, dict):
                    raise ValueError("некорректный формат state")

                raw_urls = raw.get("urls")
                urls = (
                    [url.strip() for url in raw_urls if isinstance(url, str) and url.strip()]
                    if isinstance(raw_urls, list)
                    else []
                )
                stored_sitemap_url = raw.get("sitemap_url")
                stored_base_url = raw.get("base_url")
                sitemap_url = (
                    stored_sitemap_url.strip()
                    if isinstance(stored_sitemap_url, str) and stored_sitemap_url.strip()
                    else self.sitemap_url
                )
                base_url = (
                    stored_base_url.strip()
                    if isinstance(stored_base_url, str) and stored_base_url.strip()
                    else self.base_url
                )

                cache_version = _safe_nonnegative_int(raw.get("cache_version"), 0)
                st = WikiState(

                    sitemap_url=sitemap_url,

                    base_url=base_url,

                    max_pages=_safe_nonnegative_int(raw.get("max_pages"), self.max_pages),

                    urls=urls,

                    next_idx=_safe_nonnegative_int(raw.get("next_idx"), 0),

                    done_notified=raw.get("done_notified") if isinstance(raw.get("done_notified"), bool) else False,
                    cache_version=cache_version,

                )

                config_matches = (
                    st.sitemap_url == self.sitemap_url
                    and st.base_url == self.base_url
                    and st.max_pages == self.max_pages
                )
                if st.urls and cache_version >= _INDEX_CACHE_VERSION and config_matches:

                    st.urls = _dedupe_urls(
                        st.urls + list(self.extra_urls),
                        base_url=self.base_url,
                        max_pages=self.max_pages,
                    )

                    st.next_idx = min(st.next_idx, len(st.urls))

                    return st

            except Exception:

                pass



        urls = _read_sitemap_urls(
            self.sitemap_url,
            max_pages=self.max_pages,
            base_url=self.base_url,
            extra_urls=self.extra_urls,
        )

        st = WikiState(

            sitemap_url=self.sitemap_url,

            base_url=self.base_url,

            max_pages=self.max_pages,

            urls=urls,

            next_idx=0,

            done_notified=False,
            cache_version=0,

        )

        self._save_state(st)

        return st



    def _save_state(self, st: WikiState) -> None:

        payload = {

            "sitemap_url": st.sitemap_url,

            "base_url": st.base_url,

            "max_pages": st.max_pages,

            "urls": st.urls,

            "next_idx": st.next_idx,

            "done_notified": st.done_notified,

            "cache_version": st.cache_version,

        }

        _atomic_write_text(self.state_file, json.dumps(payload, ensure_ascii=False))



    def load_cached_docs(self) -> None:

        if self._state.cache_version < _INDEX_CACHE_VERSION:

            self.index.replace_docs([])

            _atomic_write_text(self.cache_file, "[]\n")

            self._state.next_idx = 0

            self._state.done_notified = False

            self._state.cache_version = _INDEX_CACHE_VERSION

            self._save_state(self._state)

            logging.info("Старый кэш индекса сброшен для полной перестройки")

            return

        if not self.cache_file.exists():
            self._state.next_idx = 0
            self._save_state(self._state)
            return

        docs = _load_cache(self.cache_file)

        if docs:

            self.index.add_docs(docs)

            logging.info("Загружен кэш индекса: %s (страниц: %d)", self.cache_file.as_posix(), len(docs))

    def is_done(self) -> bool:

        return self._state.next_idx >= len(self._state.urls)



    def is_done_notified(self) -> bool:

        return bool(self._state.done_notified)



    def mark_done_notified(self) -> None:

        self._state.done_notified = True

        self._save_state(self._state)



    def step(self, batch_size: int) -> int:

        if self.is_done():

            return 0



        start = self._state.next_idx

        end = min(len(self._state.urls), start + max(1, batch_size))

        batch = self._state.urls[start:end]



        new_docs: list[WebWikiDoc] = []

        client = httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": "WikiLinkBot/1.0"})

        for url in batch:

            for attempt in range(3):

                try:

                    r = client.get(url)

                    if r.status_code == 200:

                        title, text = _extract_text_from_html(r.text)

                        new_docs.append(WebWikiDoc(title=title, url=url, text=text))

                        break

                    if r.status_code not in {408, 429, 500, 502, 503, 504}:

                        break

                except Exception:

                    if attempt == 2:

                        break

        client.close()



        # обновляем индекс и сохраняем кэш (append через полную перезапись — проще и надёжнее)

        self.index.add_docs(new_docs)

        self._state.next_idx = end

        self._save_state(self._state)

        _save_cache(self.cache_file, self.index_snapshot())



        logging.info("Индексирование (постепенно): %d/%d (+%d, всего в памяти: %d)",

                     end, len(self._state.urls), len(new_docs), self.index.doc_count)

        return len(new_docs)



    def index_snapshot(self) -> list[WebWikiDoc]:

        # берём срез безопасно через поиск-лок

        with self.index._lock:  # noqa: SLF001 (внутреннее использование)

            return list(self.index._docs)





def _dedupe_urls(urls: list[str], *, base_url: str, max_pages: int = 0) -> list[str]:

    result: list[str] = []

    seen: set[str] = set()

    prefix = base_url.rstrip("/")

    for raw_url in urls:

        url = raw_url.strip()

        if not url or (url != prefix and not url.startswith(prefix + "/")) or url in seen:

            continue

        seen.add(url)

        result.append(url)

        if max_pages > 0 and len(result) >= max_pages:

            break

    return result


def _read_sitemap_urls(
    sitemap_url: str,
    *,
    max_pages: int,
    base_url: str,
    extra_urls: tuple[str, ...] = (),
) -> list[str]:

    with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": "WikiLinkBot/1.0"}) as client:
        r = client.get(sitemap_url)
        r.raise_for_status()



    sitemap_text = r.text
    if len(sitemap_text.encode("utf-8")) > _MAX_SITEMAP_BYTES:
        raise ValueError("ответ sitemap превышает допустимый размер")

    root = ET.fromstring(sitemap_text)

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}



    urls: list[str] = []

    for loc in root.findall(".//sm:url/sm:loc", ns):

        if loc.text:

            url = loc.text.strip()

            if not url.startswith(base_url.rstrip("/") + "/") and url != base_url.rstrip("/"):

                continue

            urls.append(url)

    urls = _dedupe_urls(urls, base_url=base_url, max_pages=max_pages)

    for url in _dedupe_urls(list(extra_urls), base_url=base_url):
        if url not in urls:
            urls.append(url)

    return urls





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
    total = len(urls)
    with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": "WikiLinkBot/1.0"}) as client:
        for i, url in enumerate(urls, start=1):
            try:
                r = client.get(url)
                if r.status_code != 200:
                    continue
                page_text = r.text
                if len(page_text.encode("utf-8")) > _MAX_WIKI_PAGE_BYTES:
                    logging.warning("Пропущена слишком большая страница wiki: %s", url)
                    continue
                title, text = _extract_text_from_html(page_text)
                docs.append(WebWikiDoc(title=title, url=url, text=text))
            except Exception:
                continue
            if i % 50 == 0:
                logging.info("Индексирование: %d/%d (успешно: %d)", i, total, len(docs))
    if not docs:
        raise RuntimeError("Не получилось скачать страницы вики для индекса")
    return docs





def _save_cache(path: Path, docs: list[WebWikiDoc]) -> None:

    payload = [{"title": d.title, "url": d.url, "text": d.text} for d in docs]

    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False))


def _atomic_write_text(path: Path, content: str) -> None:
    """Заменяет файл целиком, не оставляя частично записанный JSON при сбое."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
        Path(temporary_name).replace(path)
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
