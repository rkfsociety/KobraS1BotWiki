from __future__ import annotations



import json

import re
import xml.etree.ElementTree as ET

from dataclasses import dataclass

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
    if re.search(r"\bзачем\s+(?:оно|тебе|вам|это|мне|нам)\b", t) and "?" not in text:
        if re.search(r"\b(?:спал\s+бы|спи\s+бы|не\s+знал\s+про|что\s+могу\s+сказать)\b", t):
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

    return bool(
        re.search(
            r"\b(как|почему|зачем|что|где|когда|кто|можно ли|помогите|не работает)\b",
            t,
        )
    )





@dataclass(frozen=True)

class WebWikiDoc:

    title: str

    url: str

    text: str





class WebWikiIndex:

    def __init__(self, docs: list[WebWikiDoc]) -> None:

        self._docs = docs

        self._blobs = [_make_search_blob(d) for d in docs]

        self._lock = threading.Lock()



    @property

    def doc_count(self) -> int:

        with self._lock:

            return len(self._docs)



    @staticmethod

    def looks_like_question(text: str) -> bool:

        return _looks_like_question(text)



    @staticmethod

    def empty() -> "WebWikiIndex":

        return WebWikiIndex([])



    def _score_one(self, q: str, doc: WebWikiDoc, blob: str) -> int:

        if not q:

            return 0

        ts = int(fuzz.token_set_ratio(q, blob))

        tr = int(fuzz.token_sort_ratio(q, blob))

        pr = int(fuzz.partial_ratio(q, blob))

        base = int(0.52 * ts + 0.33 * tr + 0.15 * pr)



        q_tokens = {t for t in q.split() if len(t) > 2 and t not in _TOKEN_BONUS_STOP}

        b_tokens = set(blob.split())

        overlap = len(q_tokens & b_tokens)

        bonus = min(26, overlap * 5)



        if any(k in q for k in ("replac", "install", "remov", "swap", "chang", "disassembl")):

            if "replacement" in doc.url or "replace" in doc.url or "install" in doc.url:

                bonus += 10



        if any(k in q for k in ("extrud", "hotend", "nozzle", "print-head", "printhead")):

            if "/faq" in doc.url or doc.url.rstrip("/").endswith("/faq"):

                bonus -= 14



        if "kobra" in q and "kobra" in blob:

            bonus += 8

        if "s1" in q_tokens and "s1" in b_tokens:

            bonus += 8

        if "combo" in q_tokens and "combo" in b_tokens:

            bonus += 8



        return max(0, min(100, base + bonus))



    def search(self, query: str, *, top_k: int = 1) -> list[tuple[WebWikiDoc, int]]:

        q = _normalize(query)

        scored: list[tuple[int, int]] = []

        with self._lock:

            blobs = list(self._blobs)

            docs = list(self._docs)

        for i, blob in enumerate(blobs):

            score = self._score_one(q, docs[i], blob)

            scored.append((score, i))

        scored.sort(reverse=True, key=lambda x: x[0])

        return [(docs[i], score) for score, i in scored[: max(1, top_k)]]



    def add_docs(self, new_docs: list[WebWikiDoc]) -> None:

        if not new_docs:

            return

        with self._lock:

            self._docs.extend(new_docs)

            self._blobs.extend(_make_search_blob(d) for d in new_docs)





@dataclass

class WikiState:

    sitemap_url: str

    base_url: str

    max_pages: int

    urls: list[str]

    next_idx: int

    done_notified: bool = False





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

    ) -> None:

        self.index = index

        self.cache_file = Path(cache_path)

        self.state_file = Path(state_path)

        self.sitemap_url = sitemap_url

        self.base_url = base_url

        self.max_pages = max_pages



        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        self.state_file.parent.mkdir(parents=True, exist_ok=True)



        self._state = self._load_or_init_state()



    def _load_or_init_state(self) -> WikiState:

        if self.state_file.exists():

            try:

                raw = json.loads(self.state_file.read_text(encoding="utf-8"))

                st = WikiState(

                    sitemap_url=str(raw.get("sitemap_url") or self.sitemap_url),

                    base_url=str(raw.get("base_url") or self.base_url),

                    max_pages=int(raw.get("max_pages") or self.max_pages),

                    urls=list(raw.get("urls") or []),

                    next_idx=int(raw.get("next_idx") or 0),

                    done_notified=bool(raw.get("done_notified") or False),

                )

                if st.urls:

                    return st

            except Exception:

                pass



        urls = _read_sitemap_urls(self.sitemap_url, max_pages=self.max_pages, base_url=self.base_url)

        st = WikiState(

            sitemap_url=self.sitemap_url,

            base_url=self.base_url,

            max_pages=self.max_pages,

            urls=urls,

            next_idx=0,

            done_notified=False,

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

        }

        self.state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")



    def load_cached_docs(self) -> None:

        if not self.cache_file.exists():

            return

        docs = _load_cache(self.cache_file)

        if docs:

            self.index.add_docs(docs)

            logging.info("Загружен кэш индекса: %s (страниц: %d)", self.cache_file.as_posix(), len(docs))

            # если кэш больше, чем next_idx — подвинем курсор вперёд

            if self._state.next_idx < len(docs):

                self._state.next_idx = len(docs)

                self._save_state(self._state)



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

            try:

                r = client.get(url)

                if r.status_code != 200:

                    continue

                title, text = _extract_text_from_html(r.text)

                new_docs.append(WebWikiDoc(title=title, url=url, text=text))

            except Exception:

                continue



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





def _read_sitemap_urls(sitemap_url: str, *, max_pages: int, base_url: str) -> list[str]:

    client = httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": "WikiLinkBot/1.0"})

    r = client.get(sitemap_url)

    r.raise_for_status()



    root = ET.fromstring(r.text)

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}



    urls: list[str] = []

    for loc in root.findall(".//sm:url/sm:loc", ns):

        if loc.text:

            url = loc.text.strip()

            if not url.startswith(base_url.rstrip("/") + "/") and url != base_url.rstrip("/"):

                continue

            urls.append(url)

            if max_pages > 0 and len(urls) >= max_pages:

                break

    return urls





def _extract_text_from_html(html: str) -> tuple[str, str]:

    soup = BeautifulSoup(html, "html.parser")

    title = (soup.title.get_text(strip=True) if soup.title else "").strip()



    for tag in soup(["script", "style", "noscript"]):

        tag.decompose()



    body = soup.body.get_text(" ", strip=True) if soup.body else soup.get_text(" ", strip=True)

    text = _normalize(f"{title}\n{body}")

    return title or "Wiki", text





def _fetch_docs(urls: list[str]) -> list[WebWikiDoc]:

    docs: list[WebWikiDoc] = []

    client = httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": "WikiLinkBot/1.0"})



    total = len(urls)

    for i, url in enumerate(urls, start=1):

        try:

            r = client.get(url)

            if r.status_code != 200:

                continue

            title, text = _extract_text_from_html(r.text)

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

    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")





def _load_cache(path: Path) -> list[WebWikiDoc]:

    try:

        raw = json.loads(path.read_text(encoding="utf-8"))

        docs: list[WebWikiDoc] = []

        for item in raw:

            title = str(item.get("title") or "").strip() or "Wiki"

            url = str(item.get("url") or "").strip()

            text = str(item.get("text") or "").strip()

            if url and text:

                docs.append(WebWikiDoc(title=title, url=url, text=text))

        return docs

    except Exception:

        return []



