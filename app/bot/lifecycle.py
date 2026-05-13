"""Точка входа: логирование, Application, индексация вики, polling."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.bot.error_display import _load_manual_error_codes
from app.bot.git_autopull import git_sync_from_remote, project_repo_root, schedule_restart_after_pull
from app.bot.handlers import (
    cmd_admincheck,
    cmd_error,
    cmd_fix,
    cmd_help,
    cmd_id,
    cmd_ping,
    cmd_qaadd,
    cmd_qadel,
    cmd_qalist,
    cmd_status,
    cmd_update,
    cmd_wiki,
    on_any_update,
    on_error,
    on_message,
)
from app.bot.manual_qa import load_manual_qa_store
from app.bot.ops_notify import notify_ops
from app.bot.stores import _load_clarify_store, _load_fix_store
from app.config import Settings, load_settings
from app.error_codes_catalog import ensure_error_codes_catalog, merge_manual_overrides
from app.resource_limits import apply_posix_virtual_memory_limit_mb
from app.web_wiki_index import WebWikiIndex, WebWikiIndexer

def main() -> None:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "bot.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    # В консоль (окно)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # В файл с ротацией (чтобы не разрастался бесконечно)
    fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.info("Лог-файл: %s", log_path.resolve())
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Подхватываем .env, если он рядом с запуском.
    load_dotenv(override=False)

    settings = load_settings()

    # До загрузки тяжёлого кэша индекса — лимит виртуальной памяти (POSIX), см. MEMORY_LIMIT_MB.
    apply_posix_virtual_memory_limit_mb(settings.memory_limit_mb)

    # Простейший лок-файл, чтобы не запустить 2 экземпляра polling одновременно.
    # Храним рядом с кэшем, чтобы путь был "рядом с ботом", а не где-то в системных папках.
    lock_path = Path(settings.cache_path).resolve().parent / "bot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            old_pid = int(lock_path.read_text(encoding="utf-8").strip())
            try:
                os.kill(old_pid, 0)
                raise RuntimeError(
                    f"Похоже, бот уже запущен (pid={old_pid}). Остановите старый процесс и запустите снова."
                )
            except OSError:
                pass
        except Exception:
            pass
    lock_path.write_text(str(os.getpid()), encoding="utf-8")

    wiki_index = WebWikiIndex.empty()
    indexer = WebWikiIndexer(
        index=wiki_index,
        cache_path=settings.cache_path,
        state_path=settings.state_path,
        sitemap_url=settings.wiki_sitemap_url,
        base_url=settings.wiki_base_url,
        max_pages=settings.wiki_max_pages,
    )
    indexer.load_cached_docs()

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["wiki_index"] = wiki_index
    app.bot_data["wiki_indexer"] = indexer
    git_pull_restart_state: dict[str, str] = {"action": "none", "cmd": ""}
    app.bot_data["git_pull_restart_state"] = git_pull_restart_state
    app.bot_data["git_update_lock"] = asyncio.Lock()
    # восстанавливаем ожидаемые уточнения после перезапуска
    try:
        store = _load_clarify_store()
        pending2: dict[tuple[int, int], dict] = {}
        for k, v in store.items():
            try:
                chat_s, user_s = k.split(":", 1)
                pending2[(int(chat_s), int(user_s))] = v
            except Exception:
                continue
        app.bot_data["clarify_pending"] = pending2
    except Exception:
        app.bot_data["clarify_pending"] = {}
    try:
        app.bot_data["manual_qa_entries"] = load_manual_qa_store()
    except Exception:
        app.bot_data["manual_qa_entries"] = []
    logging.info("Manual QA: %d записей", len(app.bot_data["manual_qa_entries"]))

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("admincheck", cmd_admincheck))
    app.add_handler(CommandHandler("wiki", cmd_wiki))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("error", cmd_error))
    app.add_handler(CommandHandler("fix", cmd_fix))
    app.add_handler(CommandHandler("qaadd", cmd_qaadd))
    app.add_handler(CommandHandler("qalist", cmd_qalist))
    app.add_handler(CommandHandler("qadel", cmd_qadel))
    app.add_handler(CommandHandler("update", cmd_update))
    # Диагностика: первым делом логируем любой update
    app.add_handler(TypeHandler(Update, on_any_update), group=-1)
    # filters.UpdateType.* здесь не используем, чтобы не "отрезать" обычные сообщения.
    # Без & ~filters.COMMAND: на части апдейтов (пустой text/caption) комбинация ломалась на PTB 21 + Py 3.14.
    # Команды всё равно отсекаются в on_message по префиксу "/" и отдельными CommandHandler.
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION), on_message))
    app.add_error_handler(on_error)

    logging.info("Бот запущен. Wiki docs: %d", wiki_index.doc_count)

    async def _post_init(application: Application) -> None:
        me = await application.bot.get_me()
        application.bot_data["bot_username"] = me.username
        application.bot_data["bot_id"] = me.id
        logging.info("Bot username: @%s", me.username)
        # Каталог ошибок (fallback, если у кода нет отдельной страницы /error-codes/<code>-code)
        try:
            manual = _load_manual_error_codes()
            scraped = await ensure_error_codes_catalog(
                base_url=settings.wiki_base_url,
                cache_path=".cache/error_codes_catalog.json",
                refresh_hours=max(1, int(settings.wiki_refresh_hours)),
            )
            application.bot_data["error_codes_catalog"] = merge_manual_overrides(scraped, manual)
            logging.info(
                "Каталог кодов ошибок загружен: %d (manual=%d)",
                len(application.bot_data["error_codes_catalog"]),
                len(manual),
            )
        except Exception as e:
            logging.warning("Не удалось загрузить каталог кодов ошибок: %s", e)
        # Локальные фиксы ссылок (/fix)
        try:
            application.bot_data["fix_store"] = _load_fix_store()
            logging.info("Fix-store загружен: %d", len(application.bot_data["fix_store"]))
        except Exception as e:
            logging.warning("Не удалось загрузить fix-store: %s", e)
        try:
            wix = application.bot_data.get("wiki_index")
            nd = wix.doc_count if wix is not None else "?"
            await notify_ops(
                application,
                f"Старт бота\n@{me.username}\nwiki_docs={nd}\npid={os.getpid()}",
            )
        except Exception as e:
            logging.warning("ops_notify при старте: %s", e)

    async def _index_step(context) -> None:
        _ = context
        idxr: WebWikiIndexer = app.bot_data["wiki_indexer"]
        st = app.bot_data["settings"]
        if idxr.is_done():
            # Если уже всё скачано — попробуем один раз отправить уведомление (если включено).
            if (
                st.notify_on_index_done
                and st.notify_chat_id is not None
                and not idxr.is_done_notified()
            ):
                mention = (st.notify_mention or "").strip()
                text = "Индексация вики завершена."
                if mention:
                    text = f"{mention} {text}"
                try:
                    await app.bot.send_message(chat_id=st.notify_chat_id, text=text)
                    idxr.mark_done_notified()
                    logging.info("Отправлено уведомление о завершении индексации в чат %s", st.notify_chat_id)
                except Exception as e:
                    logging.warning("Не удалось отправить уведомление: %s", e)
            # Всё готово — отключаем дальнейшие запуски job, чтобы не спамить логами.
            job = app.bot_data.get("index_job")
            try:
                if job:
                    job.schedule_removal()
                    app.bot_data["index_job"] = None
                    logging.info("Индексация завершена — job index_step отключён")
            except Exception:
                pass
            return
        t0 = time.time()
        # step() блокирующий (httpx sync), выполняем в отдельном потоке
        await asyncio.to_thread(idxr.step, st.index_batch_size)
        dt = time.time() - t0

        # Если после шага всё закончилось — тоже уведомим.
        if (
            idxr.is_done()
            and st.notify_on_index_done
            and st.notify_chat_id is not None
            and not idxr.is_done_notified()
        ):
            mention = (st.notify_mention or "").strip()
            text = "Индексация вики завершена."
            if mention:
                text = f"{mention} {text}"
            try:
                await app.bot.send_message(chat_id=st.notify_chat_id, text=text)
                idxr.mark_done_notified()
                logging.info("Отправлено уведомление о завершении индексации в чат %s", st.notify_chat_id)
            except Exception as e:
                logging.warning("Не удалось отправить уведомление: %s", e)

        # Если индексация завершилась на этом шаге — отключаем job.
        if idxr.is_done():
            job = app.bot_data.get("index_job")
            try:
                if job:
                    job.schedule_removal()
                    app.bot_data["index_job"] = None
                    logging.info("Индексация завершена — job index_step отключён")
            except Exception:
                pass
            return

        if not st.auto_tune_indexer:
            return

        # Автоподстройка интервала: если шаг занимает почти весь интервал — увеличиваем.
        # Если шаг очень быстрый — слегка уменьшаем (но не ниже минимума).
        cur = float(app.bot_data.get("index_interval_current", st.index_interval_seconds))
        new = cur
        if dt > cur * 0.9:
            new = min(float(st.index_interval_max_seconds), max(cur, dt * 1.5))
        elif dt < cur * 0.25:
            new = max(float(st.index_interval_min_seconds), cur * 0.8)

        # Если интервал меняется заметно — пересоздаём job.
        if abs(new - cur) >= 2.0:
            app.bot_data["index_interval_current"] = new
            job = app.bot_data.get("index_job")
            try:
                if job:
                    job.schedule_removal()
            except Exception:
                pass
            app.bot_data["index_job"] = app.job_queue.run_repeating(
                _index_step,
                interval=int(round(new)),
                first=int(round(new)),
                name="index_step",
            )
            logging.info("Автоподстройка: шаг %.1fs -> новый интервал %ss", dt, int(round(new)))

    # Периодически докачиваем новые страницы, прогресс сохраняется в .cache/
    app.bot_data["index_interval_current"] = float(settings.index_interval_seconds)
    app.bot_data["index_job"] = app.job_queue.run_repeating(
        _index_step,
        interval=settings.index_interval_seconds,
        first=1,
        name="index_step",
    )

    async def _git_autopull_job(context: ContextTypes.DEFAULT_TYPE) -> None:
        application = context.application
        st: Settings = application.bot_data["settings"]
        if not st.git_autopull_enabled:
            return
        lock = application.bot_data.get("git_update_lock")
        if lock is None:
            return
        async with lock:
            repo = project_repo_root()
            try:
                updated, msg = await asyncio.to_thread(
                    git_sync_from_remote,
                    repo=repo,
                    remote=st.git_autopull_remote,
                    branch=st.git_autopull_branch,
                    hard_reset=st.git_autopull_hard_reset,
                )
            except Exception as e:
                logging.warning("git autopull: %s", e)
                await notify_ops(application, f"git autopull: исключение при git\n{type(e).__name__}: {e}")
                return
            if not updated:
                if st.log_decisions and msg and msg != "уже актуально":
                    logging.debug("git autopull: %s", msg)
                return
            logging.info("git autopull: %s — перезапуск", msg)
            await schedule_restart_after_pull(
                application=application,
                git_pull_restart_state=application.bot_data["git_pull_restart_state"],
                restart_command=st.git_restart_command,
                log_tag="git autopull",
            )

    if settings.git_autopull_enabled:
        app.bot_data["git_autopull_job"] = app.job_queue.run_repeating(
            _git_autopull_job,
            interval=settings.git_autopull_interval_seconds,
            first=min(120, settings.git_autopull_interval_seconds),
            name="git_autopull",
        )
        logging.info(
            "Автообновление из git: каждые %s с, %s/%s, режим=%s",
            settings.git_autopull_interval_seconds,
            settings.git_autopull_remote,
            settings.git_autopull_branch,
            "reset --hard (как на GitHub)" if settings.git_autopull_hard_reset else "ff-only",
        )

    app.post_init = _post_init  # type: ignore[attr-defined]
    # Важно: после перезапуска не "догоняем" накопившиеся сообщения.
    # Telegram отдаёт накопленные updates при polling — drop_pending_updates их сбрасывает.
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

    if git_pull_restart_state.get("action") == "exec":
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        repo = project_repo_root()
        os.chdir(str(repo))
        os.execv(sys.executable, [sys.executable, "-m", "app.bot"])
    if git_pull_restart_state.get("action") == "subprocess":
        sys.exit(0)
