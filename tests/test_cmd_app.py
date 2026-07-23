import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.handlers import cmd_app
from app.bot.panel_login import cmd_start


def test_cmd_app_publishes_direct_miniapp_button():
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="supergroup", id=-100123),
        effective_message=SimpleNamespace(reply_text=reply_text),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(
            bot_data={
                "bot_username": "kobra_help_bot",
                "settings": SimpleNamespace(developer_user_ids=[]),
            }
        ),
        bot=SimpleNamespace(
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="administrator")
            )
        ),
    )

    asyncio.run(cmd_app(update, context))

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "📱 Открыть приложение"
    assert button.url == "https://t.me/kobra_help_bot?startapp"


def test_start_app_payload_opens_miniapp_button():
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_message=SimpleNamespace(reply_text=reply_text),
        effective_user=SimpleNamespace(id=42),
    )
    context = SimpleNamespace(
        args=["app"],
        application=SimpleNamespace(
            bot_data={"settings": SimpleNamespace(panel_webapp_url="https://example.test/app")}
        ),
    )

    asyncio.run(cmd_start(update, context))

    kwargs = reply_text.await_args.kwargs
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.web_app.url == "https://example.test/app"
