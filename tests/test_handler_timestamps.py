from __future__ import annotations

from app.bot.handlers._utils import _safe_runtime_timestamp


def test_safe_runtime_timestamp_handles_corrupted_values():
    assert _safe_runtime_timestamp("100.5") == 100.5
    assert _safe_runtime_timestamp("broken") == 0.0
    assert _safe_runtime_timestamp(float("nan"), default=7.0) == 7.0
    assert _safe_runtime_timestamp(float("inf")) == 0.0
