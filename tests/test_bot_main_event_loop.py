"""Регрессия запуска бота без asyncio DeprecationWarning на Python 3.12+."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.bot.lifecycle import _ensure_lock_available, _restore_clarify_pending


def test_entrypoint_installs_event_loop_without_deprecation_warning():
    code = (
        "import asyncio, warnings\n"
        "from app.bot.__main__ import _install_event_loop\n"
        "warnings.simplefilter('error', DeprecationWarning)\n"
        "loop = _install_event_loop()\n"
        "assert asyncio.get_event_loop() is loop\n"
        "loop.close()\n"
    )
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_restore_clarify_pending_skips_malformed_records():
    restored = _restore_clarify_pending({
        "-100:42": {"original": "вопрос"},
        "broken": {"original": "bad"},
        "-100:43": "broken",
    })

    assert restored == {(-100, 42): {"original": "вопрос"}}


def test_lock_check_rejects_running_process(monkeypatch, tmp_path: Path):
    lock_path = tmp_path / "bot.lock"
    lock_path.write_text("123", encoding="utf-8")
    monkeypatch.setattr("app.bot.lifecycle.os.kill", lambda pid, sig: None)

    with pytest.raises(RuntimeError, match="уже запущен"):
        _ensure_lock_available(lock_path)


def test_lock_check_allows_stale_or_malformed_lock(monkeypatch, tmp_path: Path):
    lock_path = tmp_path / "bot.lock"
    lock_path.write_text("not-a-pid", encoding="utf-8")
    _ensure_lock_available(lock_path)

    lock_path.write_text("123", encoding="utf-8")
    monkeypatch.setattr(
        "app.bot.lifecycle.os.kill",
        lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError),
    )
    _ensure_lock_available(lock_path)
