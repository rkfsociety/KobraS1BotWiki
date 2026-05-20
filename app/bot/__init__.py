"""Telegram-бот вики: пакет разбит из бывшего монолитного bot.py."""
import app.bot.layer_model_gate  # noqa: F401 — патчи до handlers

from app.bot.lifecycle import main

__all__ = ["main"]
