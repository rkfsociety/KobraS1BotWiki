import asyncio
import os

from app.bot.lifecycle import main

if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()
