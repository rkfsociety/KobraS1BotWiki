"""Уточнения модели и цепочки reply после clarify."""

from __future__ import annotations

import html

import logging

import time

from telegram import Message, Update

from telegram.constants import ParseMode

from telegram.ext import ContextTypes

from app.bot.admin_access import user_id_is_developer

from app.bot.design_replies import _maybe_reply_printer_design_vs_question

from app.bot.ephemeral import schedule_delete_slash_command_and_reply

from app.bot.error_codes_wiki import (

    _error_code_variant_suffix,

    _pick_error_code_doc,

)

from app.bot.i18n import _t

from app.bot.reply_logging import _log_bot_reply

from app.bot.decision_log import log_seen_message, log_skip

from app.ru_layer import expand_queries

from app.bot.stores import (

    _clarify_key,

    _load_clarify_store,

    _save_clarify_store,

)

from app.bot.text_heuristics import (

    _extract_error_code,

    _is_error_code_query,

    _model_slug_hints,

    _needs_model_clarification,

)

from app.bot.wiki_ranking import (

    _response_wiki_url_acceptable,

    _search_best_with_model_bias,

)

from app.config import Settings

from app.web_wiki_index import WebWikiDoc, WebWikiIndex

def _sync_clarify_pending_from_disk(pending: dict[tuple[int, int], dict]) -> None:

    """

    Подмешиваем состояние с диска в in-memory pending.

    Нужно, если ответ на уточнение обработал другой процесс (два polling на один токен)

    или память устарела относительно .cache/clarify_pending.json.

    """

    store = _load_clarify_store()

    for k, v in store.items():

        if not isinstance(v, dict):

            continue

        try:

            chat_s, user_s = str(k).split(":", 1)

            tup = (int(chat_s), int(user_s))

        except Exception:

            continue

        old = pending.get(tup)

        ts_new = float(v.get("ts") or 0.0)

        if old is None or ts_new >= float(old.get("ts") or 0.0):

            pending[tup] = v

async def _try_send_error_code_clarify(

    *,

    msg,

    context: ContextTypes.DEFAULT_TYPE,

    chat_id: int,

    text: str,

    code: str,

    candidates: list[WebWikiDoc],

    settings,

) -> bool:

    """

    Если по коду ошибки есть несколько страниц (разные модели) — просим уточнить модель.

    """

    if not settings.clarify_enabled or not msg.from_user:

        return False

    # собираем список вариантов по суффиксам URL

    suffixes: list[str] = []

    for d in candidates:

        s = _error_code_variant_suffix(code, d.url)

        if s:

            suffixes.append(s)

    uniq = sorted(set(suffixes))

    if len(uniq) < 2:

        return False

    pretty = ", ".join(uniq).upper()

    lang = context.application.bot_data.get("last_user_lang") or "ru"

    sent = await msg.reply_text(

        _t(lang, "error_code_clarify").format(code=html.escape(code), variants=html.escape(pretty)),

        parse_mode=ParseMode.HTML,

        disable_web_page_preview=True,

    )

    pending = context.application.bot_data.setdefault("clarify_pending", {})

    ckey = (chat_id, msg.from_user.id)

    now2 = time.time()

    pending[ckey] = {"original": text, "ts": now2, "prompt_message_id": sent.message_id}

    store = _load_clarify_store()

    store[_clarify_key(chat_id, msg.from_user.id)] = pending[ckey]

    _save_clarify_store(store)

    _log_bot_reply("error_code_clarify_prompt", chat_id, msg.from_user.id, message_id=sent.message_id, code=code, variants=pretty)

    return True

async def _reply_no_guide_for_model(

    msg,

    *,

    context: ContextTypes.DEFAULT_TYPE,

    chat_id: int,

    settings: Settings,

    user_id: int | None,

    best_url: str,

    hints: frozenset[str],

) -> Message:

    lang = context.application.bot_data.get('last_user_lang') or 'ru'

    sent = await msg.reply_text(_t(lang, 'no_guide_for_model'), disable_web_page_preview=True)

    if settings.log_decisions:

        log_skip(chat_id, "no_guide_for_model", msg=msg, url=best_url, hints=" ".join(sorted(hints)))

    _log_bot_reply(

        "no_matching_guide",

        chat_id,

        user_id,

        url=best_url,

        hints=" ".join(sorted(hints)),

    )

    return sent

def _arm_clarify_correction_window(

    context: ContextTypes.DEFAULT_TYPE,

    chat_id: int,

    user_id: int,

    original: str,

    settings,

) -> None:

    """После ответа на уточнение — даём несколько reply-поправок модели."""

    if not settings.clarify_enabled or settings.clarify_correction_max <= 0:

        return

    key = (chat_id, user_id)

    cd = context.application.bot_data.setdefault("clarify_correction_cooldown_until", {})

    if not user_id_is_developer(user_id, settings) and time.time() < float(cd.get(key, 0.0)):

        return

    st = context.application.bot_data.setdefault("clarify_correction_state", {})

    st[key] = {

        "original": original.strip(),

        "remaining": settings.clarify_correction_max,

        "ts": time.time(),

        # Разрешаем продолжать цепочку только reply на последний ответ бота.

        "expected_reply_to_mid": None,

    }

def _is_reply_to_bot(update: Update, *, bot_id: int | None) -> tuple[bool, int | None]:

    """

    Возвращает (is_reply_to_bot, reply_message_id).

    reply_message_id — message_id того сообщения, на которое отвечают.

    """

    msg = update.effective_message

    if not msg or not msg.reply_to_message or not msg.reply_to_message.from_user:

        return False, None

    if bot_id is None:

        return False, msg.reply_to_message.message_id

    return msg.reply_to_message.from_user.id == bot_id, msg.reply_to_message.message_id

def _reply_is_expected_by_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:

    """

    В группах игнорируем любые reply, если бот сам их не просил.

    Разрешаем только:

    - reply на уточняющий prompt (clarify_pending.prompt_message_id)

    - reply на последний ответ бота в рамках окна поправок (clarify_correction_state.expected_reply_to_mid)

    """

    msg = update.effective_message

    if not msg or not update.effective_chat or not msg.from_user:

        return False

    bot_id = context.application.bot_data.get("bot_id")

    is_reply_to_bot, reply_mid = _is_reply_to_bot(update, bot_id=bot_id)

    if not is_reply_to_bot or reply_mid is None:

        return False

    key = (update.effective_chat.id, msg.from_user.id)

    pending = context.application.bot_data.setdefault("clarify_pending", {})

    _sync_clarify_pending_from_disk(pending)

    item = pending.get(key)

    if item:

        expected_mid = item.get("prompt_message_id")

        if expected_mid is not None and int(expected_mid) == int(reply_mid):

            return True

    st = context.application.bot_data.setdefault("clarify_correction_state", {})

    corr = st.get(key)

    if corr:

        exp = corr.get("expected_reply_to_mid")

        if exp is not None and int(exp) == int(reply_mid):

            return True

    return False

async def _deliver_clarify_combined(

    msg,

    *,

    context: ContextTypes.DEFAULT_TYPE,

    combined: str,

    original: str,

    chat_id: int,

    from_user: int,

    settings,

    trace: str,

) -> str:

    """

    Общая логика после уточнения модели: справочник конструкции и поиск вики.

    trace: 'followup' | 'correction'

    Возвращает: printer_design | wiki | uncertain | no_guide

    """

    # Защита: для кодов ошибок не уточняем и не отвечаем "общими" страницами.

    # Либо находим точную страницу /error-codes/<code>-code..., либо молчим.

    if _is_error_code_query(original) or _is_error_code_query(combined):

        lang = context.application.bot_data.get("last_user_lang") or "ru"

        index: WebWikiIndex = context.application.bot_data["wiki_index"]

        code = _extract_error_code(combined) or _extract_error_code(original)

        best_doc = _pick_error_code_doc(index, code, context_text=combined) if code else None

        best_score = 100 if best_doc else -1

        if not best_doc:

            if settings.log_decisions:

                log_skip(chat_id, "error_code_not_found", msg=msg, trace=trace, score=best_score)

            return "silent"

        url = best_doc.url

        title = html.escape(best_doc.title)

        reply = (

            _t(lang, "found_in_wiki") + "\n"

            f"• <b>{title}</b>\n"

            f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"

            f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>"

        )

        sent = await msg.reply_text(reply, parse_mode=ParseMode.HTML, disable_web_page_preview=False)

        # Подстрахуемся: даже если кто-то ответит reply, мы не хотим продолжать цепочку по кодам ошибок.

        _log_bot_reply(

            "error_code_wiki",

            chat_id,

            from_user,

            score=best_score,

            url=url,

        )

        return "wiki"

    if await _maybe_reply_printer_design_vs_question(

        msg,

        question=combined,

        chat_id=chat_id,

        settings=settings,

        user_id=from_user,

    ):

        if settings.log_decisions and trace == "correction":

            logging.info(

                "clarify_correction chat=%s user=%s outcome=printer_design",

                chat_id,

                from_user,

            )

        return "printer_design"

    index: WebWikiIndex = context.application.bot_data["wiki_index"]

    variants = expand_queries(combined) if settings.ru_layer_enabled else [combined]

    best_doc, best_score = _search_best_with_model_bias(

        index, variants, context_text=combined, topic_for_keywords=original

    )

    uncertain_kind = "clarify_correction_uncertain" if trace == "correction" else "clarify_followup_uncertain"

    wiki_kind = "clarify_correction_wiki" if trace == "correction" else "clarify_followup_wiki"

    if not best_doc or best_score < settings.min_score:

        sent = await msg.reply_text(

            _t(context.application.bot_data.get("last_user_lang") or "ru", "still_uncertain"),

            disable_web_page_preview=True,

        )

        _log_bot_reply(

            uncertain_kind,

            chat_id,

            from_user,

            score=best_score if best_doc else None,

            url=(best_doc.url if best_doc else None),

        )

        # Разрешаем следующий reply только на этот ответ бота

        st = context.application.bot_data.setdefault("clarify_correction_state", {})

        if (chat_id, from_user) in st:

            st[(chat_id, from_user)]["expected_reply_to_mid"] = sent.message_id

        return "uncertain"

    if not _response_wiki_url_acceptable(combined, best_doc.url):

        await _reply_no_guide_for_model(

            msg,

            context=context,

            chat_id=chat_id,

            settings=settings,

            user_id=from_user,

            best_url=best_doc.url,

            hints=_model_slug_hints(combined),

        )

        return "no_guide"

    url = best_doc.url

    title = html.escape(best_doc.title)

    lang = context.application.bot_data.get("last_user_lang") or "ru"

    reply = (

        _t(lang, "thanks_found_in_wiki") + "\n"

        f"• <b>{title}</b>\n"

        f"<a href=\"{html.escape(url)}\">{html.escape(url)}</a>\n"

        f"<i>{html.escape(_t(lang, 'match').format(score=best_score))}</i>"

    )

    sent = await msg.reply_text(reply, parse_mode=ParseMode.HTML, disable_web_page_preview=False)

    hints = _model_slug_hints(combined)

    _log_bot_reply(

        wiki_kind,

        chat_id,

        from_user,

        score=best_score,

        url=url,

        hints=" ".join(sorted(hints)) if hints else "-",

    )

    # Разрешаем следующий reply только на этот ответ бота

    st = context.application.bot_data.setdefault("clarify_correction_state", {})

    if (chat_id, from_user) in st:

        st[(chat_id, from_user)]["expected_reply_to_mid"] = sent.message_id

    return "wiki"

def _clarify_model_hint_html(text: str) -> str:

    """

    Примеры моделей в тексте уточнения: экструдер/стол и т.д. — только FDM;

    смола/LCD — только фотополимерные; иначе оба класса отдельно (без смешивания там, где нелогично).

    """

    t = text.lower()

    fdm_kw = (

        "экструдер",

        "сопло",

        "хотэнд",

        "ремень",

        "стол",

        "куб",

        "настрой",

        "уровн",

        "подогрев",

        "сопл",

        "застрял",

        "заклинил",

        "extruder",

        "nozzle",

        "hotend",

        "hot end",

        "belt",

        "heated bed",

        "build plate",

        "jam",

        "clog",

        "stepper",

        "двер",

        "петл",

        "door",

        "hinge",

        "enclosure",

    )

    resin_kw = (

        "смол",

        "резин",

        "фотополимер",

        "ванн",

        "vat",

        "экспоз",

        "resin",

        "exposure",

        "peel",

        "fep",

    )

    is_fdm = any(k in t for k in fdm_kw)

    is_resin = any(k in t for k in resin_kw)

    if is_fdm and not is_resin:

        return "(например: <b>Kobra S1 / Kobra 3 / Vyper</b>)"

    if is_resin and not is_fdm:

        return "(например: <b>Photon Mono M5s / Photon M3 / Photon Ultra</b>)"

    return "(FDM: <b>Kobra / Vyper</b>; смола: <b>Photon / Mono</b>)"

async def _try_send_printer_clarify(

    *,

    msg,

    context: ContextTypes.DEFAULT_TYPE,

    chat_id: int,

    text: str,

    best_doc,

    best_score: int,

    settings,

    require_score_floor: bool,

    score_floor: int,

    slash_command_ephemeral: bool = False,

) -> str | None:

    """

    Если нужна модель и она не указана — отправляем уточнение (или блокируем ответ).

    Returns:

      None — уточнение не требуется, можно отвечать ссылкой

      "sent" — отправили запрос уточнения

      "blocked" — нужна модель, но cooldown; ссылку не шлём

    """

    if not settings.clarify_enabled or not msg.from_user:

        return None

    if not _needs_model_clarification(text):

        return None

    if require_score_floor and best_score < score_floor:

        return None

    cooldown = context.application.bot_data.setdefault("clarify_last_ts", {})

    ckey = (chat_id, msg.from_user.id)

    last = float(cooldown.get(ckey, 0.0))

    now2 = time.time()

    dev = user_id_is_developer(msg.from_user.id, settings)

    if not dev and now2 - last < settings.clarify_cooldown_seconds:

        if settings.log_decisions:

            log_skip(chat_id, "need_printer_model_cooldown", msg=msg, score=best_score, url=best_doc.url)

        return "blocked"

    cc_state = context.application.bot_data.setdefault("clarify_correction_state", {})

    cc_state.pop(ckey, None)

    cd = context.application.bot_data.setdefault("clarify_correction_cooldown_until", {})

    cd.pop(ckey, None)

    pending = context.application.bot_data.setdefault("clarify_pending", {})

    cooldown[ckey] = now2

    hint = _clarify_model_hint_html(text)

    lang = context.application.bot_data.get("last_user_lang") or "ru"

    sent = await msg.reply_text(

        _t(lang, "clarify_prompt").format(hint=hint),

        parse_mode=ParseMode.HTML,

        disable_web_page_preview=True,

    )

    pending[ckey] = {"original": text, "ts": now2, "prompt_message_id": sent.message_id}

    store = _load_clarify_store()

    store[_clarify_key(chat_id, msg.from_user.id)] = pending[ckey]

    _save_clarify_store(store)

    if settings.log_decisions:

        logging.info("clarify chat=%s score=%d url=%s reason=model_required mid=%s thread=%s", chat_id, best_score, best_doc.url, msg.message_id, getattr(msg, "message_thread_id", None) or "None")

    _log_bot_reply(

        "clarify_prompt",

        chat_id,

        msg.from_user.id,

        message_id=sent.message_id,

        score=best_score,

        url=best_doc.url,

    )

    if slash_command_ephemeral:

        out = _t(lang, "clarify_prompt").format(hint=hint)

        schedule_delete_slash_command_and_reply(

            context=context,

            user_msg=msg,

            bot_msg=sent,

            wiki_base_url=settings.wiki_base_url,

            outgoing_text=out,

        )

    return "sent"

async def _maybe_handle_clarification_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:

    """

    Если пользователь ответил reply на уточняющий вопрос бота — пробуем повторный поиск.

    Возвращает True, если сообщение обработано.

    """

    msg = update.effective_message

    if not msg or not msg.text or not update.effective_chat:

        return False

    settings = context.application.bot_data["settings"]

    pending = context.application.bot_data.setdefault("clarify_pending", {})

    _sync_clarify_pending_from_disk(pending)

    from_user = msg.from_user.id if msg.from_user else 0

    key = (update.effective_chat.id, from_user)

    item = pending.get(key)

    if not item:

        if settings.log_decisions and msg.reply_to_message and msg.reply_to_message.from_user:

            logging.info(

                "clarify_followup_no_pending chat=%s user=%s reply_from=%s reply_mid=%s",

                update.effective_chat.id,

                from_user,

                msg.reply_to_message.from_user.id,

                msg.reply_to_message.message_id,

            )

        return False

    # Уточнение принимаем только как reply на сообщение бота

    bot_id = context.application.bot_data.get("bot_id")

    is_reply_to_bot = False

    reply_from_id = None

    reply_msg_id = None

    if msg.reply_to_message and msg.reply_to_message.from_user:

        reply_from_id = msg.reply_to_message.from_user.id

        reply_msg_id = msg.reply_to_message.message_id

    if bot_id and reply_from_id is not None:

        is_reply_to_bot = reply_from_id == bot_id

    if not is_reply_to_bot:

        if settings.log_decisions:

            logging.info(

                "clarify_followup_ignored chat=%s user=%s bot_id=%s reply_from_id=%s has_reply=%s",

                update.effective_chat.id,

                from_user,

                bot_id,

                reply_from_id,

                str(bool(msg.reply_to_message)).lower(),

            )

        return False

    expected_mid = item.get("prompt_message_id")

    if expected_mid is not None and reply_msg_id is not None and int(expected_mid) != int(reply_msg_id):

        if settings.log_decisions:

            logging.info(

                "clarify_followup_ignored chat=%s user=%s reason=reply_to_other_message expected_mid=%s got_mid=%s",

                update.effective_chat.id,

                from_user,

                expected_mid,

                reply_msg_id,

            )

        return False

    original = str(item.get("original") or "").strip()

    if not original:

        pending.pop(key, None)

        return False

    combined = f"{original} {msg.text.strip()}"

    if settings.log_decisions:

        rmid = msg.reply_to_message.message_id if msg.reply_to_message else None

        rfrom = msg.reply_to_message.from_user.id if (msg.reply_to_message and msg.reply_to_message.from_user) else None

        log_seen_message(

            chat_id=update.effective_chat.id,

            user_id=from_user,

            msg=msg,

            has_reply=bool(msg.reply_to_message),

            reply_mid=rmid,

            reply_from=rfrom,

            text=combined,

        )

    pending.pop(key, None)

    store = _load_clarify_store()

    store.pop(_clarify_key(update.effective_chat.id, from_user), None)

    _save_clarify_store(store)

    await _deliver_clarify_combined(

        msg,

        context=context,

        combined=combined,

        original=original,

        chat_id=update.effective_chat.id,

        from_user=from_user,

        settings=settings,

        trace="followup",

    )

    _arm_clarify_correction_window(

        context,

        update.effective_chat.id,

        from_user,

        original,

        settings,

    )

    return True

async def _maybe_handle_clarify_correction_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:

    """

    Reply на любое сообщение бота после цепочки clarify: пользователь поправил модель (1–N раз), затем кулдаун.

    """

    msg = update.effective_message

    if not msg or not msg.text or not update.effective_chat or not msg.from_user:

        return False

    settings = context.application.bot_data["settings"]

    if not settings.clarify_enabled or settings.clarify_correction_max <= 0:

        return False

    chat_id = update.effective_chat.id

    from_user = msg.from_user.id

    key = (chat_id, from_user)

    bot_id = context.application.bot_data.get("bot_id")

    reply_from_id = None

    if msg.reply_to_message and msg.reply_to_message.from_user:

        reply_from_id = msg.reply_to_message.from_user.id

    if not bot_id or reply_from_id is None or reply_from_id != bot_id:

        return False

    st = context.application.bot_data.setdefault("clarify_correction_state", {})

    item = st.get(key)

    if not item:

        return False

    now = time.time()

    if now - float(item.get("ts", 0.0)) > settings.clarify_correction_ttl_seconds:

        st.pop(key, None)

        if settings.log_decisions:

            logging.info(

                "clarify_correction_expired chat=%s user=%s",

                chat_id,

                from_user,

            )

        return False

    original = str(item.get("original") or "").strip()

    if not original:

        st.pop(key, None)

        return False

    expected_mid = item.get("expected_reply_to_mid")

    if expected_mid is not None:

        # принимаем поправку только reply на последний ответ бота в цепочке

        _, reply_mid = _is_reply_to_bot(update, bot_id=bot_id)

        if reply_mid is None or int(reply_mid) != int(expected_mid):

            return False

    combined = f"{original} {msg.text.strip()}"

    if settings.log_decisions:

        rmid = msg.reply_to_message.message_id if msg.reply_to_message else None

        rfrom = msg.reply_to_message.from_user.id if (msg.reply_to_message and msg.reply_to_message.from_user) else None

        log_seen_message(

            chat_id=chat_id,

            user_id=from_user,

            msg=msg,

            has_reply=bool(msg.reply_to_message),

            reply_mid=rmid,

            reply_from=rfrom,

            text=combined,

        )

    await _deliver_clarify_combined(

        msg,

        context=context,

        combined=combined,

        original=original,

        chat_id=chat_id,

        from_user=from_user,

        settings=settings,

        trace="correction",

    )

    item["ts"] = now

    rem = int(item.get("remaining", 0)) - 1

    if rem <= 0:

        st.pop(key, None)

        if not user_id_is_developer(from_user, settings):

            cd = context.application.bot_data.setdefault("clarify_correction_cooldown_until", {})

            cd[key] = now + float(settings.clarify_cooldown_seconds)

            if settings.log_decisions:

                logging.info(

                    "clarify_correction_exhausted chat=%s user=%s cooldown_s=%s",

                    chat_id,

                    from_user,

                    settings.clarify_cooldown_seconds,

                )

    else:

        item["remaining"] = rem

        st[key] = item

    return True

