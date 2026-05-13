"""Константы и пути к локальным JSON-сторам бота."""
from __future__ import annotations

from pathlib import Path

CLARIFY_STORE = Path(".cache/clarify_pending.json")
ANSWER_CTX_STORE = Path(".cache/answer_context.json")
FEEDBACK_STORE = Path(".cache/feedback.json")
FIX_STORE = Path(".cache/fixes.json")
