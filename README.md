# Kobra S1 Bot Wiki

Telegram-бот для групп поддержки Anycubic. Читает вопросы в чате, ищет подходящую страницу в вики и отвечает ссылкой.

## Быстрый старт

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # задать TELEGRAM_BOT_TOKEN, WIKI_BASE_URL, WIKI_SITEMAP_URL
python -m app.bot
```

## Документация

- [Настройка (.env)](docs/configuration.md)
- [Веб-панель](docs/web-panel.md)
- [Архитектура](docs/architecture.md)
- [Эксплуатация](docs/ops.md)
