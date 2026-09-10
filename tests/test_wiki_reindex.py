from __future__ import annotations

import json

from app.bot.wiki_reindex import SitemapMonitor


def test_sitemap_state_save_is_atomic(tmp_path):
    monitor = SitemapMonitor("https://example.test/sitemap.xml", cache_dir=tmp_path)
    monitor._state["hash"] = "abc"

    monitor._save_state()

    assert json.loads(monitor.state_file.read_text(encoding="utf-8"))["hash"] == "abc"
    assert not list(tmp_path.glob(".*.tmp"))
