"""Регрессия запуска бота без asyncio DeprecationWarning на Python 3.12+."""

from __future__ import annotations

import subprocess
import sys


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
