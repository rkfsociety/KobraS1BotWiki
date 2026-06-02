from __future__ import annotations



import logging

import os

import re

import shlex

import sys

from dataclasses import dataclass

from pathlib import Path



from app.default_developers import DEFAULT_DEVELOPER_USER_IDS

from app.default_ephemeral_exempt import DEFAULT_EPHEMERAL_EXEMPT_CHAT_IDS

from app.default_ops_chat import DEFAULT_OPS_NOTIFY_CHAT_ID





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

    #: 0 = не ограничивать. Linux/macOS: RLIMIT_AS (виртуальная память процесса), см. app/resource_limits.py

    memory_limit_mb: int

    #: Фоновый git fetch (по умолчанию выкл.; ручное обновление — команда /update)

    git_autopull_enabled: bool

    #: True: git reset --hard на remote/ветку (приоритет файлов с GitHub). False: только ff-only merge

    git_autopull_hard_reset: bool

    git_autopull_interval_seconds: int

    git_autopull_remote: str

    git_autopull_branch: str

    #: Shell-команда перезапуска после pull (Linux). Пусто = os.execv на тот же -m app.bot

    git_restart_command: str | None

    #: После /qaadd и /qadel — git commit + push ``data/manual_qa.json`` (по умолчанию вкл.; выкл.: MANUAL_QA_GIT_PUSH=0)

    manual_qa_git_push: bool

    #: Разработчики: служебные команды в группах как у админа; без антиспама и без кулдаунов clarify (см. DEVELOPER_USER_IDS)

    developer_user_ids: frozenset[int]

    #: Не автоудалять пару «команда+ответ» в этих чатах (личка не удаляется всегда; см. EPHEMERAL_EXEMPT_CHAT_IDS)

    ephemeral_exempt_chat_ids: frozenset[int]

    #: Служебный чат: ошибки, перезапуски, старт бота (0/off в .env — выкл.; см. OPS_NOTIFY_CHAT_ID)

    ops_notify_chat_id: int | None

    #: Дублировать в OPS_NOTIFY_CHAT_ID всё, что пишется в консоль (logging INFO+)

    ops_log_mirror_enabled: bool

    #: Уровень зеркала: DEBUG, INFO, WARNING, …

    ops_log_mirror_level: int

    #: Как часто сливать буфер лога в Telegram (сек)

    ops_log_mirror_interval_seconds: int

    #: Перед обработкой вики-сообщения проверять getChatMember (бот может писать в чат/тему)

    require_can_reply: bool

    #: TTL кэша результата проверки (сек), при REQUIRE_CAN_REPLY=1

    reply_access_cache_seconds: int

    reply_review_mention: str

    #: Эмодзи-реакции, которые считаем «ответ плохой» (см. NEGATIVE_REACTION_EMOJIS)
    negative_reaction_emojis: frozenset[str]

    #: Логировать негативную реакцию только если её поставил админ/разработчик (REACTION_LOG_ADMIN_ONLY)
    reaction_log_admin_only: bool





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

    memory_limit_mb = _get_int("MEMORY_LIMIT_MB", 0)



    # GIT_AUTOPULL_ENABLED=1 — фоновая проверка (по умолчанию выкл.); обновление вручную: /update

    git_autopull_enabled = _get_bool("GIT_AUTOPULL_ENABLED", False)

    git_autopull_hard_reset = _get_bool("GIT_AUTOPULL_HARD_RESET", True)

    # Публичный GitHub + remote https:// — fetch без токена; приватный репо — настройте SSH/credentials

    git_autopull_interval_seconds = max(60, _get_int("GIT_AUTOPULL_INTERVAL_SECONDS", 300))

    git_autopull_remote = (os.getenv("GIT_AUTOPULL_REMOTE") or "origin").strip() or "origin"

    git_autopull_branch = (os.getenv("GIT_AUTOPULL_BRANCH") or "master").strip() or "master"

    git_restart_raw = (os.getenv("GIT_RESTART_COMMAND") or "").strip()

    if git_restart_raw:

        git_restart_command = git_restart_raw

    elif sys.platform != "win32":

        repo = _project_root()

        log_rel = ".cache/restart.log"

        git_restart_command = (

            f"cd {shlex.quote(str(repo))} && ./restart-bot.sh >> {log_rel} 2>&1 "

            f"|| ./ensure-bot.sh >> {log_rel} 2>&1"

        )

    else:

        git_restart_command = None



    manual_qa_git_push = _get_bool("MANUAL_QA_GIT_PUSH", True)



    # DEVELOPER_USER_IDS: дополнительные user_id через запятую. Всегда включён дефолтный список (см. DEFAULT_DEVELOPER_USER_IDS).

    developer_raw = (os.getenv("DEVELOPER_USER_IDS") or "").strip()

    developer_extra: set[int] = set()

    if developer_raw:

        try:

            developer_extra = {int(x.strip()) for x in developer_raw.split(",") if x.strip()}

        except ValueError:

            logging.warning("Некорректный формат DEVELOPER_USER_IDS, игнорируем доп. id")

            developer_extra = set()



    developer_user_ids = frozenset(DEFAULT_DEVELOPER_USER_IDS | developer_extra)



    ephemeral_raw = (os.getenv("EPHEMERAL_EXEMPT_CHAT_IDS") or "").strip()

    ephemeral_extra: set[int] = set()

    if ephemeral_raw:

        try:

            ephemeral_extra = {int(x.strip()) for x in ephemeral_raw.split(",") if x.strip()}

        except ValueError:

            logging.warning("Некорректный формат EPHEMERAL_EXEMPT_CHAT_IDS, игнорируем доп. id")

            ephemeral_extra = set()

    ephemeral_exempt_chat_ids = frozenset(DEFAULT_EPHEMERAL_EXEMPT_CHAT_IDS | ephemeral_extra)



    raw_ops = (os.getenv("OPS_NOTIFY_CHAT_ID") or "").strip()

    if raw_ops.lower() in ("0", "off", "false", "no", "disable", "-"):

        ops_notify_chat_id = None

    elif raw_ops:

        try:

            ops_notify_chat_id = int(raw_ops)

        except ValueError:

            logging.warning("Некорректный OPS_NOTIFY_CHAT_ID, используем дефолт %s", DEFAULT_OPS_NOTIFY_CHAT_ID)

            ops_notify_chat_id = DEFAULT_OPS_NOTIFY_CHAT_ID

    else:

        ops_notify_chat_id = DEFAULT_OPS_NOTIFY_CHAT_ID



    ops_log_mirror_enabled = _get_bool(

        "OPS_LOG_MIRROR_ENABLED",

        ops_notify_chat_id is not None,

    )

    ops_log_mirror_level_name = (os.getenv("OPS_LOG_MIRROR_LEVEL") or "INFO").strip().upper()

    ops_log_mirror_level = getattr(logging, ops_log_mirror_level_name, logging.INFO)

    ops_log_mirror_interval_seconds = max(1, _get_int("OPS_LOG_MIRROR_INTERVAL_SECONDS", 2))



    require_can_reply = _get_bool("REQUIRE_CAN_REPLY", False)



    reply_access_cache_seconds = max(1, _get_int("REPLY_ACCESS_CACHE_SECONDS", 300))



    reply_review_mention = (os.getenv("REPLY_REVIEW_MENTION") or "rkfsociety").strip()

    raw_neg = os.getenv("NEGATIVE_REACTION_EMOJIS")
    if raw_neg is None:
        negative_reaction_emojis = frozenset({"💩", "👎"})
    else:
        negative_reaction_emojis = frozenset(
            tok for tok in re.split(r"[\s,]+", raw_neg.strip()) if tok
        )

    reaction_log_admin_only = _get_bool("REACTION_LOG_ADMIN_ONLY", True)



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

        memory_limit_mb=memory_limit_mb,

        git_autopull_enabled=git_autopull_enabled,

        git_autopull_hard_reset=git_autopull_hard_reset,

        git_autopull_interval_seconds=git_autopull_interval_seconds,

        git_autopull_remote=git_autopull_remote,

        git_autopull_branch=git_autopull_branch,

        git_restart_command=git_restart_command,

        manual_qa_git_push=manual_qa_git_push,

        developer_user_ids=developer_user_ids,

        ephemeral_exempt_chat_ids=ephemeral_exempt_chat_ids,

        ops_notify_chat_id=ops_notify_chat_id,

        ops_log_mirror_enabled=ops_log_mirror_enabled,

        ops_log_mirror_level=ops_log_mirror_level,

        ops_log_mirror_interval_seconds=ops_log_mirror_interval_seconds,

        require_can_reply=require_can_reply,

        reply_access_cache_seconds=reply_access_cache_seconds,

        reply_review_mention=reply_review_mention,

        negative_reaction_emojis=negative_reaction_emojis,

        reaction_log_admin_only=reaction_log_admin_only,

    )

