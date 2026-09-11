"""Отслеживание изменений sitemap и автопереиндексация вики."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx


class SitemapMonitor:
    """Мониторит sitemap на предмет изменений (хеш, количество URL, временные метки)."""

    def __init__(self, sitemap_url: str, cache_dir: str | Path = ".cache") -> None:
        self.sitemap_url = sitemap_url
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.cache_dir / "sitemap_state.json"
        self._state = self._load_state()
        self._check_lock = asyncio.Lock()

    def _load_state(self) -> dict[str, Any]:
        """Загружает сохранённое состояние sitemap."""
        defaults = {"hash": None, "url_count": 0, "timestamp": 0.0, "last_check": 0.0}
        if self.state_file.exists():
            try:
                raw = json.loads(self.state_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    state = defaults.copy()
                    sitemap_hash = raw.get("hash")
                    if sitemap_hash is None or isinstance(sitemap_hash, str):
                        state["hash"] = sitemap_hash
                    url_count = raw.get("url_count")
                    if isinstance(url_count, int) and not isinstance(url_count, bool) and url_count >= 0:
                        state["url_count"] = url_count
                    for key in ("timestamp", "last_check"):
                        value = raw.get(key)
                        try:
                            value = float(value)
                        except (TypeError, ValueError, OverflowError):
                            continue
                        if math.isfinite(value) and value >= 0:
                            state[key] = value
                    return state
            except Exception:
                pass
        return defaults

    def _save_state(self) -> None:
        """Сохраняет состояние sitemap на диск."""
        _atomic_write_text(self.state_file, json.dumps(self._state, ensure_ascii=False))

    async def check_for_changes(self) -> tuple[bool, str]:
        """Проверяет sitemap, не допуская параллельных запросов и записей state."""
        async with self._check_lock:
            return await self._check_for_changes()

    async def _check_for_changes(self) -> tuple[bool, str]:
        """
        Проверяет, изменился ли sitemap.

        Returns:
            (has_changes, reason) — True если обнаружены изменения, строка с причиной.
        """
        # Время последней проверки нужно для runtime-наблюдения, но не должно
        # заставлять переписывать state-файл при каждом неизменном опросе.
        self._state["last_check"] = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(self.sitemap_url, headers={"User-Agent": "WikiBot/1.0"})
                response.raise_for_status()
                content = response.text

            # Вычисляем хеш контента sitemap
            new_hash = hashlib.sha256(content.encode()).hexdigest()
            new_url_count = content.count("<loc>")

            old_hash = self._state.get("hash")
            old_url_count = self._state.get("url_count", 0)

            # Проверяем изменения
            if new_hash != old_hash:
                reason = f"Sitemap изменился (хеш: {old_hash[:8] if old_hash else 'нет'}… → {new_hash[:8]}…)"
                self._state["hash"] = new_hash
                self._state["url_count"] = new_url_count
                self._state["timestamp"] = time.time()
                self._save_state()
                return True, reason

            if new_url_count != old_url_count:
                reason = f"Количество страниц в sitemap изменилось ({old_url_count} → {new_url_count})"
                self._state["hash"] = new_hash
                self._state["url_count"] = new_url_count
                self._state["timestamp"] = time.time()
                self._save_state()
                return True, reason

            return False, "Sitemap без изменений"

        except Exception as e:
            logging.error("Ошибка при проверке sitemap: %s", e)
            return False, f"Ошибка: {e}"


class WikiReindexer:
    """Управляет переиндексацией вики при обнаружении изменений."""

    def __init__(self, indexer: Any, notify_callback: Any | None = None) -> None:
        """
        Args:
            indexer: Экземпляр WebWikiIndexer.
            notify_callback: Async функция для уведомлений (application, message).
        """
        self.indexer = indexer
        self.notify_callback = notify_callback
        self._reindex_in_progress = False
        self._reindex_lock = asyncio.Lock()

    async def reindex_if_needed(self, monitor: SitemapMonitor, force: bool = False) -> bool:
        """
        Проверяет sitemap и переиндексирует, если нужно.

        Args:
            monitor: Экземпляр SitemapMonitor.
            force: Если True, переиндексирует даже без изменений.

        Returns:
            True если переиндексация произведена.
        """
        async with self._reindex_lock:
            if self._reindex_in_progress:
                logging.info("Переиндексация уже в процессе, пропускаем")
                return False
            self._reindex_in_progress = True
        try:
            has_changes, reason = await monitor.check_for_changes()
            if not (has_changes or force):
                return False

            logging.info("Инициирована переиндексация вики: %s", reason)

            # Очищаем состояние: сбрасываем next_idx и удаляем флаг done_notified
            self.indexer._state.next_idx = 0
            self.indexer._state.done_notified = False
            self.indexer._state.urls = []
            self.indexer.index.replace_docs([])
            _atomic_write_text(self.indexer.cache_file, "[]\n")
            self.indexer._state.cache_version = 2
            self.indexer._save_state(self.indexer._state)

            # Перезагружаем список URL из sitemap
            from app.web_wiki_index import _read_sitemap_urls

            new_urls = await asyncio.to_thread(
                _read_sitemap_urls,
                self.indexer.sitemap_url,
                max_pages=self.indexer.max_pages,
                base_url=self.indexer.base_url,
                extra_urls=self.indexer.extra_urls,
            )

            self.indexer._state.urls = new_urls
            self.indexer._save_state()

            msg = f"✅ Переиндексация начата: {len(new_urls)} страниц в очереди. {reason}"
            logging.info(msg)

            if self.notify_callback:
                try:
                    await self.notify_callback(msg)
                except Exception as e:
                    logging.warning("Не удалось отправить уведомление: %s", e)

            return True

        except Exception as e:
            logging.error("Ошибка при переиндексации: %s", e)
            if self.notify_callback:
                try:
                    await self.notify_callback(f"❌ Ошибка при переиндексации: {e}")
                except Exception:
                    pass
            return False

        finally:
            self._reindex_in_progress = False


def _atomic_write_text(path: Path, content: str) -> None:
    """Заменяет state/cache целиком, не оставляя частичный файл при сбое."""
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
