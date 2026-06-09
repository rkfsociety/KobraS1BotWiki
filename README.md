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

## Дорожная карта

### Качество поиска
- [x] Сбор вопросов без ответа (`score < MIN_SCORE`) в отдельный файл для анализа и пополнения `manual_qa.json`
- [ ] Кэш поисковых результатов — LRU-кэш для повторяющихся вопросов
- [ ] Семантический поиск на основе векторных embeddings (вместо чистого fuzzy matching)

### Аналитика
- [ ] Статистика в веб-панели: топ вопросов, топ страниц вики, пик активности по времени
- [ ] Счётчик вопросов без ответа с возможностью просмотра в панели

### Эксплуатация
- [ ] Health check endpoint (`/health`) — HTTP 200/503 для внешнего мониторинга
- [ ] Автопереиндексация при обновлении вики (по webhook или сравнению sitemap)

### Технический долг
- [ ] Разбить `text_heuristics.py` (4300+ строк) на подмодули по темам
- [ ] Разбить `handlers.py` (3000+ строк) на подмодули
