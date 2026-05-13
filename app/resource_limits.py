"""Ограничения процесса (POSIX)."""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def apply_posix_virtual_memory_limit_mb(limit_mb: int) -> None:
    """
    Жёсткий потолок виртуальной памяти процесса (Linux/macOS): RLIM_AS.

    Срабатывает при превышении: malloc/mmap начнут падать с MemoryError / процесс может получить SIGKILL от ядра.
    На Windows не поддерживается — используйте лимиты службы (systemd, Docker).

    Вызывать как можно раньше после старта интерпретатора, до загрузки больших JSON в память.
    """
    if limit_mb <= 0:
        return
    if sys.platform == "win32":
        log.warning("MEMORY_LIMIT_MB задан (%s), но на Windows RLIMIT_AS не применяется.", limit_mb)
        return
    try:
        import resource
    except ImportError:
        log.warning("Модуль resource недоступен, MEMORY_LIMIT_MB пропущен.")
        return

    limit = int(limit_mb) * 1024 * 1024
    if limit < 64 * 1024 * 1024:
        log.warning("MEMORY_LIMIT_MB=%s слишком мал — минимум для стабильности обычно 128.", limit_mb)

    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        log.info("Установлен лимит виртуальной памяти (RLIMIT_AS): %s МиБ", limit_mb)
    except ValueError as e:
        log.warning(
            "MEMORY_LIMIT_MB=%s не применён (текущее использование адресного пространства выше лимита?): %s",
            limit_mb,
            e,
        )
    except OSError as e:
        log.warning("MEMORY_LIMIT_MB=%s: setrlimit не удался: %s", limit_mb, e)
