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

Локальная память агента (SSH, деплой): `.cursor/memories.md` — не в git, создаётся на машине разработчика.

Разбор `data/missed_questions.json`: пополнение `manual_qa.json`, эвристики в `app/bot/heuristics/_banter.py`, затем очистка файла.

## Дорожная карта

### Качество поиска
- [x] Сбор вопросов без ответа (`score < MIN_SCORE`) в отдельный файл для анализа и пополнения `manual_qa.json`
- [x] Кэш поисковых результатов — LRU-кэш для повторяющихся вопросов (500 записей, сброс при переиндексации)
- [ ] Семантический поиск на основе векторных embeddings (вместо чистого fuzzy matching)
- [x] Авто-предложение записей в `manual_qa.json` на основе часто повторяющихся вопросов без ответа

### Аналитика
- [x] Статистика в веб-панели: топ страниц вики по ответам, топ вопросов по частоте, активность по часам
- [x] Отдельная страница `/missed` в панели для удобного просмотра большого списка вопросов без ответа

### Веб-панель
- [x] Пагинация в ленте последних ответов (25 записей на страницу)

### Эксплуатация
- [x] Health check endpoint (`/health`) — HTTP 200/503 для внешнего мониторинга
- [x] Автопереиндексация при обновлении вики (мониторинг sitemap + webhook `/api/webhook/reindex`)

### Технический долг
- [x] Разбить `text_heuristics.py` (4300+ строк) на подмодули по темам → пакет `app/bot/heuristics/`
- [x] Разбить `handlers.py` (3000+ строк) на подмодули → пакет `app/bot/handlers/`
