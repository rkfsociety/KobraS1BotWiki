# Kobra S1 Bot Wiki

Telegram-бот для группы поддержки Anycubic. Читает сообщения, ищет релевантную страницу в вики по `WIKI_SITEMAP_URL` и, если совпадение достаточно хорошее, отвечает ссылкой.

Инструкция для пользователей чата: [`wiki/getting-started.md`](wiki/getting-started.md)

---

## Быстрый старт

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env   # заполнить TELEGRAM_BOT_TOKEN, WIKI_BASE_URL, WIKI_SITEMAP_URL
python -m app.bot
```

На Linux/macOS: `source .venv/bin/activate`, `cp .env.example .env`, `./start-bot.sh`.

> Файл `.env` не коммитить — он в `.gitignore`.

---

## Основные команды бота

| Команда | Что делает |
|---------|-----------|
| `/help` | Справка (для участников и администраторов) |
| `/wiki <запрос>` | Поиск по вики напрямую |
| `/id` | ID и тип текущего чата |
| `/status` | Диагностика: разрешён ли чат/тема |
| `/ping` | Проверка связи |
| `/error` | Reply на ответ бота — плохой ответ, перепоиск |
| `/fix <url>` | Reply на ответ бота — указать правильную ссылку |
| `/qaadd`, `/qalist`, `/qadel` | Ручные Q&A (`data/manual_qa.json`) |
| `/update` | Обновить код с GitHub и перезапустить |

Служебные команды в группах доступны только **администраторам чата** и пользователям из `DEVELOPER_USER_IDS`. В личке доступны всем.

---

## Документация

| Файл | Содержание |
|------|-----------|
| [`docs/configuration.md`](docs/configuration.md) | Все переменные `.env`, пороги, чаты, индексация |
| [`docs/web-panel.md`](docs/web-panel.md) | Веб-панель администратора (вход, возможности, настройки) |
| [`docs/architecture.md`](docs/architecture.md) | Структура кода, модули, алгоритм поиска |
| [`docs/ops.md`](docs/ops.md) | Логи, служебный чат, git, тесты, systemd |

---

## Тесты

```bash
pip install pytest pytest-cov
python -m pytest tests/ -v
```

CI: `ruff`, `bandit`, `pip-audit` + pytest (`.github/workflows/ci.yml`).
