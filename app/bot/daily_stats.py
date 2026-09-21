"""Ежедневная отправка статистики групп в общую тему форума."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.bot.bot_stats import get_daily_stats, get_daily_top_topics
from app.bot.daily_summary import format_daily_summary
from app.bot.topic_classifier import classify_daily_topics, select_topic_models
from app.bot.review_mention import record_outgoing_bot_message

log = logging.getLogger(__name__)

try:
    DAILY_STATS_TIMEZONE = ZoneInfo("Europe/Kaliningrad")
except ZoneInfoNotFoundError:  # pragma: no cover - зависит от tzdata окружения
    DAILY_STATS_TIMEZONE = timezone(timedelta(hours=2), name="Europe/Kaliningrad")
DAILY_STATS_SEND_TIME = time(hour=0, minute=5, tzinfo=DAILY_STATS_TIMEZONE)


def configured_daily_stats_chat_ids(settings: object) -> tuple[int, ...]:
    """Возвращает чаты для ежедневной сводки без смешивания их статистики."""
    allowed_chat_ids = getattr(settings, "allowed_chat_ids", None)
    if allowed_chat_ids is not None:
        return tuple(sorted(int(chat_id) for chat_id in allowed_chat_ids))

    panel_chat_id = getattr(settings, "panel_admin_chat_id", None)
    if isinstance(panel_chat_id, int) and not isinstance(panel_chat_id, bool) and panel_chat_id != 0:
        return (panel_chat_id,)
    return ()


def _previous_local_day() -> str:
    today = datetime.now(DAILY_STATS_TIMEZONE).date()
    return (today - timedelta(days=1)).isoformat()


async def send_daily_stats(context) -> None:
    """Отправляет вчерашнюю сводку отдельно в General каждого настроенного чата."""
    application = context.application
    settings = application.bot_data.get("settings", SimpleNamespace())
    chat_ids = configured_daily_stats_chat_ids(settings)
    if not chat_ids:
        log.info("Ежедневная статистика не отправлена: чаты не настроены")
        return

    bot_data = application.bot_data
    day = _previous_local_day()
    chat_store = bot_data.get("chat_store")
    topic_models: tuple[str, ...] = ()
    if chat_store is not None and getattr(settings, "literouter_enabled", False) and getattr(
        settings, "literouter_api_key", ""
    ):
        topic_models = await select_topic_models(settings)
        log.info("Модели тематизации на запуск %s: %s", day, ", ".join(topic_models) or "нет")

    for chat_id in chat_ids:
        if chat_store is not None:
            try:
                await classify_daily_topics(
                    chat_store,
                    settings,
                    chat_id=chat_id,
                    day=day,
                    limit=3,
                    models=topic_models or None,
                )
            except Exception:
                log.exception("Не удалось классифицировать темы chat_id=%s day=%s", chat_id, day)
        daily = get_daily_stats(bot_data, chat_id=chat_id, topic_id=None, day=day)
        topics = get_daily_top_topics(bot_data, chat_id=chat_id, topic_id=None, day=day, limit=3)
        summary = format_daily_summary(
            day=day,
            scope_label="группе",
            scope_key=f"{chat_id}:all",
            total_incoming=daily["total_incoming"],
            topics=topics,
        )
        send_kwargs = {
            "chat_id": chat_id,
            "text": summary,
            "disable_web_page_preview": True,
        }
        try:
            get_chat = getattr(context.bot, "get_chat", None)
            chat = await get_chat(chat_id) if callable(get_chat) else None
            daily_stats_topic_id = max(0, int(getattr(settings, "daily_stats_topic_id", 0)))
            if getattr(chat, "is_forum", False) and daily_stats_topic_id > 0:
                send_kwargs["message_thread_id"] = daily_stats_topic_id
            sent = await context.bot.send_message(**send_kwargs)
            if chat_store is not None:
                record_outgoing_bot_message(
                    chat_store,
                    sent,
                    chat_id=chat_id,
                    topic_id=send_kwargs.get("message_thread_id"),
                    text=summary,
                    source="daily_stats",
                )
            log.info("Ежедневная статистика отправлена: chat_id=%s day=%s", chat_id, day)
        except Exception as exc:
            # Ошибка в одном чате не должна блокировать отправку в остальные.
            log.warning("Не удалось отправить ежедневную статистику в chat_id=%s: %s", chat_id, exc)
