"""Ответы из справочника конструкции (без вики)."""
from __future__ import annotations

import logging

from telegram import Message

from app.bot.reply_logging import log_bot_reply_for_message
from app.bot.text_heuristics import _model_slug_hints
from app.printer_catalog import explain_door_vs_design

async def _maybe_reply_printer_design_vs_question(
    msg,
    *,
    question: str,
    chat_id: int,
    settings,
    user_id: int | None,
) -> Message | None:
    """Справочник конструкции: например дверь камеры на открытой Kobra 3 — объясняем без вики."""
    hints_d = _model_slug_hints(question)
    expl = explain_door_vs_design(question, hints_d)
    if not expl:
        return None
    sent = await msg.reply_text(expl, disable_web_page_preview=True)
    log_bot_reply_for_message(
        "printer_design_fact",
        msg=msg,
        reply_text=expl,
        sent=sent,
        user_id=user_id,
        hints=" ".join(sorted(hints_d)),
    )
    return sent
