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
    if not isinstance(body, dict):
        return 400, {"status": "error", "message": "Invalid JSON body"}

    secret = body.get("secret", "")

    # Простая защита: требуем secret из окружения
    webhook_secret = os.getenv("WIKI_REINDEX_SECRET", "")
    if not webhook_secret or secret != webhook_secret:
        log.warning("wiki_reindex webhook: неверный secret")
        return 401, {"status": "error", "message": "Unauthorized"}

    bot_data = getattr(application, "bot_data", None)
    if not isinstance(bot_data, dict):
        log.warning("wiki_reindex webhook: application или bot_data недоступны")
        return 503, {"status": "error", "message": "Application not ready"}

    # Обновление только ставится в checkpoint-очередь. Сетевой обход выполняет
    # отдельная индексная job, поэтому webhook не зависит от доступности sitemap.
    reindexer = bot_data.get("wiki_reindexer")
    indexer = getattr(reindexer, "indexer", None)
    if indexer is None or not callable(getattr(indexer, "request_refresh", None)):
        log.warning("wiki_reindex webhook: indexer недоступен")
        return 503, {"status": "error", "message": "Reindexer not available"}
    try:
        snapshot = indexer.status_snapshot()
        already_active = snapshot.get("status") in {"queued", "running", "waiting-retry", "waiting-robots"}
        accepted = indexer.request_refresh(source="webhook")
        if not accepted:
            already_active = True
        snapshot = indexer.status_snapshot()
        job_status = "already_running" if already_active else "queued"
        return 200, {
            "status": "ok",
            "job_status": job_status,
            "message": "Обновление уже выполняется" if already_active else "Обновление поставлено в очередь",
            "queued": snapshot.get("queued", 0),
            "documents": snapshot.get("documents", 0),
        }

    except Exception as e:
        log.error("wiki_reindex webhook: исключение: %s", e)
        return 500, {"status": "error", "message": str(e)}
