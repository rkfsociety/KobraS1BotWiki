"""Ответы из справочника конструкции (без вики)."""
from __future__ import annotations

import logging

from app.bot.reply_logging import _log_bot_reply
from app.bot.text_heuristics import _model_slug_hints
from app.printer_catalog import explain_door_vs_design

async def _maybe_reply_printer_design_vs_question(
    msg,
    *,
    question: str,
    chat_id: int,
    settings,
    user_id: int | None,
) -> bool:
    """Справочник конструкции: например дверь камеры на открытой Kobra 3 — объясняем без вики."""
    hints_d = _model_slug_hints(question)
    expl = explain_door_vs_design(question, hints_d)
    if not expl:
        return False
    await msg.reply_text(expl, disable_web_page_preview=True)
    if settings.log_decisions:
        logging.info(
            "bot_reply kind=printer_design_fact chat=%s hints=%s",
            chat_id,
            " ".join(sorted(hints_d)),
        )
    _log_bot_reply("printer_design_fact", chat_id, user_id, hints=" ".join(sorted(hints_d)))
    return True
