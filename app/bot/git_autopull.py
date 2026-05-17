"""Обновление кода из git и перезапуск процесса бота.

- Ручная команда **/update** (только админы): ``git fetch`` + синхронизация с remote и перезапуск.
- Опциональный фоновый режим: ``GIT_AUTOPULL_ENABLED=1`` (по умолчанию выключен).

Переменные окружения (см. app/config.py):
- GIT_AUTOPULL_ENABLED — фоновая проверка (по умолчанию выкл.); включить: 1 / true
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
import sys
from pathlib import Path

from telegram.ext import Application

from app.bot.ops_notify import notify_ops


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
        logging.info("git: reset --hard -> %s", short)
        return True, f"reset --hard -> {short}"

    if before == remote_head:
        return False, "уже актуально"

    mg = run(["git", "merge", "--ff-only", f"{remote}/{branch}"])
    if mg.returncode != 0:
        return False, f"git merge --ff-only: {mg.stderr.strip() or mg.stdout.strip()}"

    short_before = before[:8]
    short_after = remote_head[:8]
    logging.info("git: %s -> %s", short_before, short_after)
    return True, f"fast-forward {short_before} -> {short_after}"


def git_ping_compare_with_remote(
    *,
    repo: Path,
    remote: str,
    branch: str,
    fetch_timeout: float = 25.0,
) -> tuple[str | None, str | None, bool | None, str | None]:
    """
    Для /ping: текущий HEAD и сравнение с remote/ветка после ``git fetch`` (без изменения рабочей копии).

    Возвращает (local_full_hash, remote_full_or_none, update_available, error_message).
    ``update_available`` True если после успешного fetch ``HEAD != remote/branch``; False если равны; None если сравнить не удалось.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    def run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    if not (repo / ".git").exists():
        return None, None, None, "no .git"

    h = run(["git", "rev-parse", "HEAD"], 12.0)
    if h.returncode != 0:
        err = (h.stderr or h.stdout or "").strip() or "rev-parse HEAD failed"
        return None, None, None, err
    local = h.stdout.strip()

    fe = run(["git", "fetch", remote, branch], fetch_timeout)
    if fe.returncode != 0:
        err = (fe.stderr or fe.stdout or "").strip() or "git fetch failed"
        return local, None, None, err

    rh = run(["git", "rev-parse", f"{remote}/{branch}"], 12.0)
    if rh.returncode != 0:
        err = (rh.stderr or rh.stdout or "").strip() or f"no {remote}/{branch} after fetch"
        return local, None, None, err

    remote_h = rh.stdout.strip()
    return local, remote_h, local != remote_h, None


async def schedule_restart_after_pull(
    *,
    application: Application,
    git_pull_restart_state: dict[str, str],
    restart_command: str | None,
    log_tag: str = "git",
) -> None:
    """
    После успешного pull: на Linux — отложенный ./restart-bot.sh (screen stop+start).
    На Windows без GIT_RESTART_COMMAND — os.execv.
    """
    repo = project_repo_root()
    cmd = (restart_command or "").strip()
    log_file = repo / ".cache" / "restart.log"

    if cmd and sys.platform != "win32":
        git_pull_restart_state["action"] = "subprocess"
        git_pull_restart_state["cmd"] = cmd
        mode_desc = f"через 3 с: restart-bot.sh (лог: {log_file.name})"
        shell_cmd = f"sleep 3 && {cmd}"
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as lf:
                lf.write(f"\n--- schedule_restart ({log_tag}) ---\n")
            subprocess.Popen(
                ["/bin/bash", "-lc", shell_cmd],
                cwd=str(repo),
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logging.error("%s: не удалось запустить GIT_RESTART_COMMAND: %s", log_tag, e)
            git_pull_restart_state["action"] = "none"
            await notify_ops(
                application,
                f"Перезапуск ({log_tag}): не удалось запустить перезапуск\n{type(e).__name__}: {e}",
            )
            return
    else:
        if cmd and sys.platform == "win32":
            logging.warning("%s: GIT_RESTART_COMMAND на Windows не поддерживается, используется os.execv", log_tag)
        git_pull_restart_state["action"] = "exec"
        mode_desc = "exec python -m app.bot (только Windows / fallback)"

    await notify_ops(application, f"Перезапуск ({log_tag})\n{mode_desc}")

    try:
        await application.stop()
    except Exception as e:
        logging.warning("%s: application.stop(): %s", log_tag, e)
