import asyncio
import os

import app.bot.layer_model_gate  # noqa: F401 — патчи до handlers

from app.bot.lifecycle import main


def _install_event_loop() -> asyncio.AbstractEventLoop:
    """Создаёт цикл явно, не вызывая устаревающий get_event_loop()."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    _install_event_loop()
    main()
