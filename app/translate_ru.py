from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import httpx


_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass
class Translator:
    cache_path: Path
    ttl_seconds: int = 180 * 24 * 3600  # 180 дней
    max_cache_entries: int = 5000

    def __post_init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            if not self.cache_path.exists():
                self._cache = {}
                return
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self._cache = raw if isinstance(raw, dict) else {}
        except Exception:
            self._cache = {}

    def _save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # кэш — необязательный; если диск/права сломаны, просто молчим
            return

    def _get_cached(self, text: str) -> str | None:
        self._load()
        ent = self._cache.get(text)
        if not isinstance(ent, dict):
            return None
        ts = float(ent.get("ts") or 0.0)
        if ts and (time.time() - ts) > float(self.ttl_seconds):
            return None
        val = ent.get("ru")
        return str(val) if isinstance(val, str) and val.strip() else None

    def _put_cached(self, text: str, ru: str, *, source: str) -> None:
        self._load()
        self._cache[text] = {"ru": ru, "ts": time.time(), "source": source}
        # примитивная защита от разрастания
        if len(self._cache) > int(self.max_cache_entries):
            for k in sorted(self._cache.keys())[: max(100, len(self._cache) - self.max_cache_entries)]:
                self._cache.pop(k, None)
        self._save()

    def should_translate(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if _CYRILLIC_RE.search(t):
            return False
        if not _LATIN_RE.search(t):
            return False
        # слишком короткие строки часто переводятся плохо/бессмысленно
        if len(t) < 6:
            return False
        return True

    async def translate_en_ru(self, text: str) -> str:
        """
        Бесплатный перевод EN->RU через публичное API MyMemory.
        - Без ключа, но с лимитами; поэтому есть кэш.
        - Если API недоступно — возвращаем исходный текст.
        """
        t = (text or "").strip()
        if not self.should_translate(t):
            return t
        if os.getenv("DISABLE_TRANSLATION", "").strip().lower() in {"1", "true", "yes", "y", "on"}:
            return t

        cached = self._get_cached(t)
        if cached:
            return cached

        q = urllib.parse.quote(t, safe="")
        url = f"https://api.mymemory.translated.net/get?q={q}&langpair=en|ru"
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "KobraS1BotWiki/1.0"})
                r.raise_for_status()
                data = r.json()
            resp = data.get("responseData", {}) if isinstance(data, dict) else {}
            ru = resp.get("translatedText") if isinstance(resp, dict) else None
            ru_s = str(ru).strip() if isinstance(ru, str) else ""
            if not ru_s:
                return t
            # иногда сервис возвращает тот же EN — не кэшируем мусор
            if ru_s.lower() == t.lower():
                return t
            self._put_cached(t, ru_s, source="mymemory")
            return ru_s
        except Exception:
            return t

