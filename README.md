# Kobra S1 Bot Wiki

Telegram-бот для групп поддержки Anycubic. Читает вопросы в чате, ищет подходящую страницу в вики и отвечает ссылкой.

## Быстрый старт

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.lock
cp .env.example .env
cp .env.secrets.example .env.secrets   # заполнить секреты отдельно
python -m app.bot
```

`requirements.txt` содержит диапазоны версий для обновления зависимостей, а
`requirements.lock` — проверенный набор точных версий для воспроизводимого запуска.

## Документация

- [Настройка (.env)](docs/configuration.md)
- [Веб-панель](docs/web-panel.md)
- [Архитектура](docs/architecture.md)
- [Эксплуатация](docs/ops.md)

Разбор очереди `missed_questions` в `data/chat.sqlite3`: пополнение `manual_qa`, правки эвристик в `app/bot/heuristics/_banter.py`, затем очистка очереди.

Разбор «отвеченных»: состояния `recent_replies` и `bad_answers` в той же базе через веб-панель; скрипт `scripts/apply_replies_jun2026_qa.py` (июнь 2026).

## Дорожная карта

В репозитории 74 тестовых файла; проверки запускаются через `pytest`, Ruff,
Bandit и `pip-audit` в CI.

Windows-совместимость тестов и lock/atomic-write проверок описана в
`.codex/windows-test-compatibility.md`.

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
