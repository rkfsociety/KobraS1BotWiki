from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

from app.bot.wiki_reindex_handler import handle_reindex_webhook
from app.bot.wiki_reindex import SitemapMonitor, WikiReindexer, _atomic_write_text


def test_sitemap_state_save_is_atomic(tmp_path):
    monitor = SitemapMonitor("https://example.test/sitemap.xml", cache_dir=tmp_path)
    monitor._state["hash"] = "abc"

    monitor._save_state()

    assert json.loads(monitor.state_file.read_text(encoding="utf-8"))["hash"] == "abc"
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_writer_survives_concurrent_replacements(tmp_path):
    path = tmp_path / "shared.json"

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: _atomic_write_text(path, json.dumps({"value": i})), range(32)))

    assert json.loads(path.read_text(encoding="utf-8"))["value"] in range(32)
    assert not list(tmp_path.glob(".*.tmp"))


def test_sitemap_monitor_falls_back_for_non_object_state(tmp_path):
    path = tmp_path / "sitemap_state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    monitor = SitemapMonitor("https://example.test/sitemap.xml", cache_dir=tmp_path)

    assert monitor._state["hash"] is None
    assert monitor._state["url_count"] == 0


def test_sitemap_checks_are_serialized(tmp_path, monkeypatch):
    monitor = SitemapMonitor("https://example.test/sitemap.xml", cache_dir=tmp_path)
    active = 0
    max_active = 0

    async def fake_check():
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1
        return False, "без изменений"

    monkeypatch.setattr(monitor, "_check_for_changes", fake_check)

    async def run_checks():
        return await asyncio.gather(monitor.check_for_changes(), monitor.check_for_changes())

    asyncio.run(run_checks())

    assert max_active == 1


def test_parallel_reindex_requests_do_not_duplicate_sitemap_check(tmp_path, monkeypatch):
    monitor = SitemapMonitor("https://example.test/sitemap.xml", cache_dir=tmp_path)
    reindexer = WikiReindexer(indexer=None)
    checks = 0

    async def fake_check():
        nonlocal checks
        checks += 1
        await asyncio.sleep(0)
        return False, "без изменений"

    monkeypatch.setattr(monitor, "check_for_changes", fake_check)

    async def run_requests():
        return await asyncio.gather(
            reindexer.reindex_if_needed(monitor),
            reindexer.reindex_if_needed(monitor),
        )

    assert asyncio.run(run_requests()) == [False, False]
    assert checks == 1


def test_reindex_webhook_rejects_non_object_body(monkeypatch):
    monkeypatch.setenv("WIKI_REINDEX_SECRET", "secret")

    status, payload = handle_reindex_webhook(["broken"], None)

    assert status == 400
    assert payload["status"] == "error"


def test_reindex_webhook_reports_application_not_ready(monkeypatch):
    monkeypatch.setenv("WIKI_REINDEX_SECRET", "secret")

    status, payload = handle_reindex_webhook({"secret": "secret"}, SimpleNamespace())

    assert status == 503
    assert payload["message"] == "Application not ready"
