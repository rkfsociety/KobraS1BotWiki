"""HTTP-обработчик для webhook переиндексации вики."""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)


def handle_reindex_webhook(body: dict[str, Any], application: Any) -> tuple[int, dict[str, Any]]:
    """
    Обработчик POST /api/webhook/reindex для веб-панели.

    Ожидает JSON: {"secret": "WEBHOOK_SECRET"}

    Args:
        body: Распарсенное JSON тело запроса.
        application: Экземпляр telegram.ext.Application.

    Returns:
        (status_code, response_dict) для возврата как JSON.
    """
    secret = body.get("secret", "")

    # Простая защита: требуем secret из окружения
    webhook_secret = os.getenv("WIKI_REINDEX_SECRET", "")
    if not webhook_secret or secret != webhook_secret:
        log.warning("wiki_reindex webhook: неверный secret")
        return 401, {"status": "error", "message": "Unauthorized"}

    # Получаем переиндексер и монитор
    reindexer = application.bot_data.get("wiki_reindexer")
    monitor = application.bot_data.get("sitemap_monitor")

    if not reindexer or not monitor:
        log.warning("wiki_reindex webhook: reindexer или monitor недоступны")
        return 503, {"status": "error", "message": "Reindexer not available"}

    # Отправляем в asyncio loop (вызывается из синхронного контекста)
    import asyncio

    try:
        loop = application.bot_data.get("main_loop")
        if not loop:
            return 503, {"status": "error", "message": "No event loop available"}

        # Запускаем async задачу в фоновом loop
        future = asyncio.run_coroutine_threadsafe(
            reindexer.reindex_if_needed(monitor, force=True),
            loop,
        )
        success = future.result(timeout=5.0)  # Ждём до 5 секунд

        log.info("wiki_reindex webhook: успешно (переиндексация=%s)", success)
        return 200, {
            "status": "ok",
            "message": "Переиндексация инициирована" if success else "Переиндексация уже идёт",
        }

    except Exception as e:
        log.error("wiki_reindex webhook: исключение: %s", e)
        return 500, {"status": "error", "message": str(e)}
