"""Автообновление кода из git и перезапуск процесса бота.

Переменные окружения (см. app/config.py):
- GIT_AUTOPULL_ENABLED — по умолчанию включено; выключить: 0 / false
- GIT_AUTOPULL_HARD_RESET — по умолчанию 1: после fetch выполняется ``git reset --hard`` на
  ветку remote (рабочая копия совпадает с GitHub, локальные правки в отслеживаемых файлах сбрасываются).
  Выключить (0): только ``git merge --ff-only`` — без сброса локальных изменений при том же коммите.
- GIT_AUTOPULL_INTERVAL_SECONDS, GIT_AUTOPULL_REMOTE, GIT_AUTOPULL_BRANCH
- GIT_RESTART_COMMAND — см. app/config.py

Для публичного репозитория на GitHub обычно достаточно remote вида ``https://github.com/...``
— ``git fetch`` не требует токена. Приватный репо — нужен SSH-ключ или credential helper.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path


def project_repo_root() -> Path:
    """Корень репозитория (родитель каталога app/)."""
    return Path(__file__).resolve().parents[2]


def git_sync_from_remote(
    *,
    repo: Path,
    remote: str,
    branch: str,
    hard_reset: bool,
) -> tuple[bool, str]:
    """
    git fetch, затем либо ``git reset --hard remote/branch`` (приоритет файлов с remote),
    либо ``git merge --ff-only`` (если hard_reset=False).

    Возвращает (нужен_ли_перезапуск_процесса, краткое сообщение для лога).
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    if not (repo / ".git").exists():
        return False, "нет каталога .git — пропуск"

    r_head = run(["git", "rev-parse", "HEAD"])
    if r_head.returncode != 0:
        return False, f"git rev-parse HEAD: {r_head.stderr.strip() or r_head.stdout.strip()}"

    before = r_head.stdout.strip()
    st = run(["git", "status", "--porcelain"])
    had_dirty = bool((st.stdout or "").strip()) if st.returncode == 0 else False

    fe = run(["git", "fetch", remote, branch])
    if fe.returncode != 0:
        return False, f"git fetch: {fe.stderr.strip() or fe.stdout.strip()}"

    r_rh = run(["git", "rev-parse", f"{remote}/{branch}"])
    if r_rh.returncode != 0:
        return False, f"git rev-parse {remote}/{branch}: {r_rh.stderr.strip()}"

    remote_head = r_rh.stdout.strip()

    if hard_reset:
        if before == remote_head and not had_dirty:
            return False, "уже актуально"
        rs = run(["git", "reset", "--hard", f"{remote}/{branch}"])
        if rs.returncode != 0:
            return False, f"git reset --hard: {rs.stderr.strip() or rs.stdout.strip()}"
        short = remote_head[:8]
        logging.info("git autopull: reset --hard -> %s", short)
        return True, f"reset --hard -> {short}"

    if before == remote_head:
        return False, "уже актуально"

    mg = run(["git", "merge", "--ff-only", f"{remote}/{branch}"])
    if mg.returncode != 0:
        return False, f"git merge --ff-only: {mg.stderr.strip() or mg.stdout.strip()}"

    short_before, short_after = before[:8], remote_head[:8]
    logging.info("git autopull: fast-forward %s -> %s", short_before, short_after)
    return True, f"fast-forward {short_before} -> {short_after}"
