from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _project_root() -> Path:
    # app/config.py -> app/ -> <repo root>
    return Path(__file__).resolve().parents[1]


def _resolve_path(p: str) -> str:
    path = Path(p)
    if path.is_absolute():
        return str(path)
    return str((_project_root() / path).resolve())


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    wiki_base_url: str
    wiki_sitemap_url: str
    cache_path: str
    state_path: str
    wiki_refresh_hours: int
    wiki_max_pages: int
    min_score: int
    top_k: int
    questions_only: bool
    allowed_chat_ids: frozenset[int] | None
    allowed_topic_ids: frozenset[int] | None
    cooldown_seconds: int
    max_replies_per_minute: int
    duplicate_window_seconds: int
    index_batch_size: int
    index_interval_seconds: int
    require_trigger: bool
    auto_tune_indexer: bool
    index_interval_min_seconds: int
    index_interval_max_seconds: int
    log_all_messages: bool
    log_decisions: bool
    notify_on_index_done: bool
    notify_chat_id: int | None
    notify_mention: str
    ru_layer_enabled: bool
    clarify_enabled: bool
    clarify_min_score: int
    clarify_cooldown_seconds: int
    #: Сколько раз подряд можно поправить модель ответом на бота после clarify / ответа по конструкции
    clarify_correction_max: int
    #: Окно (сек), в течение которого принимаются такие поправки (обновляется при каждой попытке)
    clarify_correction_ttl_seconds: int


def load_settings() -> Settings:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в .env / переменных окружения. Создайте .env на основе .env.example")

    wiki_base = (os.getenv("WIKI_BASE_URL") or "").strip().rstrip("/")
    if not wiki_base:
        raise RuntimeError("Не задан WIKI_BASE_URL в .env / переменных окружения")

    sitemap_url = (os.getenv("WIKI_SITEMAP_URL") or "").strip()
    if not sitemap_url:
        raise RuntimeError("Не задан WIKI_SITEMAP_URL в .env / переменных окружения")

    cache_path = _resolve_path((os.getenv("CACHE_PATH") or ".cache/wiki_index.json").strip())
    state_path = _resolve_path((os.getenv("STATE_PATH") or ".cache/wiki_state.json").strip())
    wiki_refresh_hours = _get_int("WIKI_REFRESH_HOURS", 24)
    wiki_max_pages = _get_int("WIKI_MAX_PAGES", 2000)
    min_score = _get_int("MIN_SCORE", 72)
    top_k = _get_int("TOP_K", 1)
    questions_only = _get_bool("QUESTIONS_ONLY", True)
    cooldown_seconds = _get_int("COOLDOWN_SECONDS", 20)
    max_replies_per_minute = _get_int("MAX_REPLIES_PER_MINUTE", 6)
    duplicate_window_seconds = _get_int("DUPLICATE_WINDOW_SECONDS", 1800)
    index_batch_size = _get_int("INDEX_BATCH_SIZE", 20)
    index_interval_seconds = _get_int("INDEX_INTERVAL_SECONDS", 5)
    require_trigger = _get_bool("REQUIRE_TRIGGER", True)
    auto_tune_indexer = _get_bool("AUTO_TUNE_INDEXER", True)
    index_interval_min_seconds = _get_int("INDEX_INTERVAL_MIN_SECONDS", 5)
    index_interval_max_seconds = _get_int("INDEX_INTERVAL_MAX_SECONDS", 120)
    log_all_messages = _get_bool("LOG_ALL_MESSAGES", False)
    log_decisions = _get_bool("LOG_DECISIONS", True)
    notify_on_index_done = _get_bool("NOTIFY_ON_INDEX_DONE", True)
    notify_chat_id_raw = (os.getenv("NOTIFY_CHAT_ID") or "").strip()
    notify_chat_id = int(notify_chat_id_raw) if notify_chat_id_raw else None
    notify_mention = (os.getenv("NOTIFY_MENTION") or "").strip()
    ru_layer_enabled = _get_bool("RU_LAYER_ENABLED", True)
    clarify_enabled = _get_bool("CLARIFY_ENABLED", True)
    clarify_min_score = _get_int("CLARIFY_MIN_SCORE", 55)
    clarify_cooldown_seconds = _get_int("CLARIFY_COOLDOWN_SECONDS", 300)
    clarify_correction_max = _get_int("CLARIFY_CORRECTION_MAX", 2)
    clarify_correction_ttl_seconds = _get_int("CLARIFY_CORRECTION_TTL_SECONDS", 600)

    # Загрузка списка разрешённых chat_id и topic_id из переменных окружения
    # ALLOWED_CHAT_IDS: список ID чатов через запятую (например, "123456789,-987654321")
    # ALLOWED_TOPIC_IDS: список ID тем через запятую (например, "10,20,30")
    allowed_chat_ids_raw = (os.getenv("ALLOWED_CHAT_IDS") or "").strip()
    allowed_chat_ids: frozenset[int] | None = None
    if allowed_chat_ids_raw:
        try:
            allowed_chat_ids = frozenset(int(x.strip()) for x in allowed_chat_ids_raw.split(",") if x.strip())
        except ValueError:
            logging.warning("Некорректный формат ALLOWED_CHAT_IDS, игнорируем")
            allowed_chat_ids = None

    allowed_topic_ids_raw = (os.getenv("ALLOWED_TOPIC_IDS") or "").strip()
    allowed_topic_ids: frozenset[int] | None = None
    if allowed_topic_ids_raw:
        try:
            allowed_topic_ids = frozenset(int(x.strip()) for x in allowed_topic_ids_raw.split(",") if x.strip())
        except ValueError:
            logging.warning("Некорректный формат ALLOWED_TOPIC_IDS, игнорируем")
            allowed_topic_ids = None

    return Settings(
        telegram_bot_token=token,
        wiki_base_url=wiki_base,
        wiki_sitemap_url=sitemap_url,
        cache_path=cache_path,
        state_path=state_path,
        wiki_refresh_hours=wiki_refresh_hours,
        wiki_max_pages=wiki_max_pages,
        min_score=min_score,
        top_k=top_k,
        questions_only=questions_only,
        allowed_chat_ids=allowed_chat_ids,
        allowed_topic_ids=allowed_topic_ids,
        cooldown_seconds=cooldown_seconds,
        max_replies_per_minute=max_replies_per_minute,
        duplicate_window_seconds=duplicate_window_seconds,
        index_batch_size=index_batch_size,
        index_interval_seconds=index_interval_seconds,
        require_trigger=require_trigger,
        auto_tune_indexer=auto_tune_indexer,
        index_interval_min_seconds=index_interval_min_seconds,
        index_interval_max_seconds=index_interval_max_seconds,
        log_all_messages=log_all_messages,
        log_decisions=log_decisions,
        notify_on_index_done=notify_on_index_done,
        notify_chat_id=notify_chat_id,
        notify_mention=notify_mention,
        ru_layer_enabled=ru_layer_enabled,
        clarify_enabled=clarify_enabled,
        clarify_min_score=clarify_min_score,
        clarify_cooldown_seconds=clarify_cooldown_seconds,
        clarify_correction_max=clarify_correction_max,
        clarify_correction_ttl_seconds=clarify_correction_ttl_seconds,
    )
