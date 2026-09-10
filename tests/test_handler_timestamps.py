from __future__ import annotations

from collections import deque

from app.bot.handlers._utils import (
    _rate_limit_dict,
    _rate_limit_queue,
    _rate_limit_url_dict,
    _safe_runtime_timestamp,
)


def test_safe_runtime_timestamp_handles_corrupted_values():
    assert _safe_runtime_timestamp("100.5") == 100.5
    assert _safe_runtime_timestamp("broken") == 0.0
    assert _safe_runtime_timestamp(float("nan"), default=7.0) == 7.0
    assert _safe_runtime_timestamp(float("inf")) == 0.0


def test_rate_limit_helpers_recover_corrupted_state():
    state = {
        "reply_ts_by_chat": "broken",
        "last_url_ts_by_chat": [],
        "last_reply_ts_by_chat": None,
    }

    assert isinstance(_rate_limit_dict(state, "last_reply_ts_by_chat"), dict)
    assert isinstance(_rate_limit_queue(state, 1), deque)
    assert isinstance(_rate_limit_url_dict(state, 1), dict)
