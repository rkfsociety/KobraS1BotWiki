from __future__ import annotations

import asyncio
import json

from app.bot.wiki_reindex import SitemapMonitor


def test_sitemap_state_save_is_atomic(tmp_path):
    monitor = SitemapMonitor("https://example.test/sitemap.xml", cache_dir=tmp_path)
    monitor._state["hash"] = "abc"

    monitor._save_state()

    assert json.loads(monitor.state_file.read_text(encoding="utf-8"))["hash"] == "abc"
    assert not list(tmp_path.glob(".*.tmp"))


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
