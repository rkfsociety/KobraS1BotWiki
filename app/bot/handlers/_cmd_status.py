"""Команды /ping и /status."""
from __future__ import annotations

import asyncio
import html
import time

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import ContextTypes

from app.bot.ephemeral import schedule_delete_slash_command_and_reply
from app.bot.git_autopull import git_ping_compare_with_remote, project_repo_root
from app.bot.i18n import _lang_from_message, _t
from app.bot.reply_access import chat_topic_in_allowed_lists
from app.bot.reply_logging import log_bot_reply_for_message
from app.web_wiki_index import WebWikiIndex

from ._utils import _deny_unless_admin_command_access


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return

    if await _deny_unless_admin_command_access(update, context, command="ping"):
        return

    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))
    repo = project_repo_root()
    remote = settings.git_autopull_remote
    branch = settings.git_autopull_branch
    cache_key = f"{remote}/{branch}"
    ping_git_cache: dict = context.application.bot_data.setdefault("ping_git_cache", {})
    now = time.time()
    ttl = 60.0
    ent = ping_git_cache.get(cache_key)

    if isinstance(ent, dict) and now - float(ent.get("ts", 0)) < ttl:
        local_f = ent.get("local")
        remote_f = ent.get("remote")
        upd = ent.get("upd")
        gerr = ent.get("err")
    else:
        local_f, remote_f, upd, gerr = await asyncio.to_thread(
            git_ping_compare_with_remote,
            repo=repo,
            remote=remote,
            branch=branch,
        )
        ping_git_cache[cache_key] = {"ts": now, "local": local_f, "remote": remote_f, "upd": upd, "err": gerr}

    git_lines: list[str] = []

    if local_f:
        git_lines.append(
            f"{html.escape(_t(lang, 'ping_commit_running'))}: <code>{html.escape(local_f)}</code>"
        )

    if gerr:
        git_lines.append(html.escape(_t(lang, "ping_git_fail").format(detail=gerr[:400])))
    elif remote_f is not None and upd is not None:
        git_lines.append(
            html.escape(_t(lang, "ping_commit_upstream").format(remote=remote, branch=branch))
            + ": <code>"
            + html.escape(remote_f)
            + "</code>"
        )
        if upd:
            git_lines.append(html.escape(_t(lang, "ping_update_suggest")))
        else:
            git_lines.append(
                html.escape(_t(lang, "ping_git_ok").format(remote=remote, branch=branch))
            )

    git_block = ("\n" + "\n".join(git_lines)) if git_lines else ""

    text = (
        _t(lang, "ping") + "\n"
        f"chat_id: <code>{update.effective_chat.id}</code>\n"
        f"wiki_docs: <code>{index.doc_count}</code>\n"
        f"QUESTIONS_ONLY: <code>{settings.questions_only}</code>\n"
        f"REQUIRE_TRIGGER: <code>{settings.require_trigger}</code>"
        + git_block
    )

    sent = await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    schedule_delete_slash_command_and_reply(
        context=context,
        user_msg=msg,
        bot_msg=sent,
        wiki_base_url=settings.wiki_base_url,
        outgoing_text=text,
    )

    uid = msg.from_user.id if msg.from_user else None
    log_bot_reply_for_message("cmd_ping", msg=msg, reply_text=text, sent=sent, user_id=uid)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_chat:
        return

    if await _deny_unless_admin_command_access(update, context, command="status"):
        return

    settings = context.application.bot_data["settings"]
    index: WebWikiIndex = context.application.bot_data["wiki_index"]
    msg = update.effective_message
    lang = _lang_from_message(context=context, msg=msg, text=(msg.text or msg.caption or ""))
    chat_id = update.effective_chat.id
    message_thread_id = update.effective_message.message_thread_id if update.effective_message else None

    # Дополнительная диагностика: проверяем chat.type для групп с темами
    chat_type = update.effective_chat.type
    is_supergroup_with_topics = (
        chat_type == ChatType.SUPERGROUP
        and getattr(update.effective_chat, 'is_forum', False)
    )

    # Альтернативный способ получить topic_id: если message_thread_id None,
    # но мы в форуме, возможно это общая тема (General)
    actual_topic_id = message_thread_id
    topic_source = "message_thread_id"

    # Если message_thread_id None, но чат является форумом, это может быть общая тема
    if message_thread_id is None and is_supergroup_with_topics:
        # В форумах Telegram общая тема "General" обычно имеет thread_id = 1
        # Но API может возвращать None для сообщений в General
        actual_topic_id = None  # Остаётся None, так как это действительно "общий чат" форума
        topic_source = "general_forum_topic"

    # Проверка разрешённых чатов и тем для /status (отвечает везде, но показывает статус доступа)
    allowed_chats = settings.allowed_chat_ids
    allowed_topics = settings.allowed_topic_ids

    # Специальная обработка: если allowed_topics содержит 0, это означает "только общая тема General"
    # В этом случае actual_topic_id должен быть None (что и есть для General)
    allow_general_only = allowed_topics is not None and 0 in allowed_topics

    is_chat_allowed = (allowed_chats is None) or (chat_id in allowed_chats)

    if allow_general_only:
        # Разрешаем только если message_thread_id is None (общая тема)
        is_topic_allowed = actual_topic_id is None
    else:
        # Обычная логика: разрешаем если topic_id в списке или список не задан
        is_topic_allowed = (allowed_topics is None) or (actual_topic_id is not None and actual_topic_id in allowed_topics)

    is_allowed = chat_topic_in_allowed_lists(
        allowed_chat_ids=allowed_chats,
        allowed_topic_ids=allowed_topics,
        chat_id=chat_id,
        topic_id=actual_topic_id,
    )

    bot_username = context.application.bot_data.get("bot_username")
    text = (
        _t(lang, "bot_status") + "\n"
        f"bot: <code>@{html.escape(str(bot_username or ''))}</code>\n"
        f"chat_id: <code>{chat_id}</code>\n"
        f"chat_type: <code>{chat_type}</code>\n"
        f"is_forum: <code>{str(getattr(update.effective_chat, 'is_forum', False)).lower()}</code>\n"
    )

    if actual_topic_id is not None:
        text += f"topic_id: <code>{actual_topic_id}</code> (source: {topic_source})\n"
    elif is_supergroup_with_topics:
        text += "topic_id: <code>(общая тема General)</code>\n"
    else:
        text += "topic_id: <code>(нет, сообщение не в теме)</code>\n"

    # Форматируем список разрешённых чатов/тем для отображения
    allowed_chats_str = ",".join(str(x) for x in sorted(allowed_chats)) if allowed_chats else "(не заданы)"
    allowed_topics_str = ",".join(str(x) for x in sorted(allowed_topics)) if allowed_topics else "(не заданы)"

    text += (
        f"ALLOWED_CHAT_IDS: <code>{allowed_chats_str}</code>\n"
        f"ALLOWED_TOPIC_IDS: <code>{allowed_topics_str}</code>\n"
        f"chat_allowed: <code>{str(is_chat_allowed).lower()}</code>\n"
        f"topic_allowed: <code>{str(is_topic_allowed).lower()}</code>\n"
        f"is_allowed: <code>{str(is_allowed).lower()}</code>\n"
        f"wiki_docs: <code>{index.doc_count}</code>\n"
        f"QUESTIONS_ONLY: <code>{str(settings.questions_only).lower()}</code>\n"
        f"REQUIRE_TRIGGER: <code>{str(settings.require_trigger).lower()}</code>\n"
        f"RU_LAYER_ENABLED: <code>{str(settings.ru_layer_enabled).lower()}</code>\n"
        f"CLARIFY_ENABLED: <code>{str(settings.clarify_enabled).lower()}</code>\n"
        f"CLARIFY_CORRECTION_MAX: <code>{settings.clarify_correction_max}</code>\n"
        f"CLARIFY_CORRECTION_TTL_SECONDS: <code>{settings.clarify_correction_ttl_seconds}</code>\n"
        f"LOG_DECISIONS: <code>{str(settings.log_decisions).lower()}</code>"
    )

    reply_msg = await msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    uid = msg.from_user.id if msg.from_user else None
    log_bot_reply_for_message("cmd_status", msg=msg, reply_text=text, sent=reply_msg, user_id=uid)

    schedule_delete_slash_command_and_reply(
        context=context,
        user_msg=msg,
        bot_msg=reply_msg,
        wiki_base_url=settings.wiki_base_url,
        outgoing_text=text,
    )
