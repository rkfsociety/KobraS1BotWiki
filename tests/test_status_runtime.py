from __future__ import annotations

from app.bot.handlers._utils import _safe_runtime_timestamp


def test_status_cache_timestamp_fallback_is_safe():
    assert _safe_runtime_timestamp("broken") == 0.0
    assert _safe_runtime_timestamp(float("nan")) == 0.0
