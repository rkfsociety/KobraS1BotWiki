# Архитектура

## Как работает поиск

1. Из `WIKI_SITEMAP_URL` берётся список страниц; они скачиваются и кэшируются
2. Индексация идёт пакетами в фоне (`INDEX_BATCH_SIZE`, `INDEX_INTERVAL_SECONDS`)
3. Для русских вопросов при `RU_LAYER_ENABLED=true` запрос расширяется английскими ключевыми словами (`app/ru_layer.py`)
4. Считается похожесть (RapidFuzz `token_set_ratio`) + эвристики по модели принтера, URL и кодам ошибок
5. **Приоритет источников**: ручные Q&A → дизайн-справочник → каталог кодов ошибок → поиск по индексу вики
6. Если лучший результат ≥ `MIN_SCORE` — бот отвечает ссылкой
7. Если score между `CLARIFY_MIN_SCORE` и `MIN_SCORE` — задаётся уточняющий вопрос о модели принтера

## Модули `app/bot/`

Точка входа: `python -m app.bot` → `app/bot/__main__.py` → `app/bot/lifecycle.py`

| Модуль | Роль |
|--------|------|
| `lifecycle.py` | Логирование, `Application`, индексация, polling |
| `handlers.py` | Команды и обработка входящих сообщений |
| `text_heuristics.py` | Эвристики: определение модели, темы, кода ошибки, фильтр болтовни |
| `wiki_ranking.py` | Поиск по индексу с бонусами/штрафами по URL и модели |
| `error_codes_wiki.py` | Выбор страницы `/error-codes/...` |
| `error_display.py` | Карточки кодов ошибок и перевод |
| `design_replies.py` | Короткие текстовые ответы из справочника (ACE, TPU, резонанс/PA, слайсер) |
| `clarify.py` | Уточнение модели и цепочки reply |
| `layer_model_gate.py` | Отсев кандидатов вики по модели принтера |
| `manual_qa.py` | Ручные Q&A (`/qaadd`, `data/manual_qa.json`) |
| `user_context.py` | Контекст диалога: история сообщений, обогащение запросов анафорой |
| `bad_answers.py` | Хранение/загрузка ошибочных ответов (`data/bad_answers.json`) |
| `reply_logging.py` | Лог исходящих ответов; персистентная лента (`.cache/recent_replies.json`) |
| `decision_log.py` | Ссылки на сообщения в чате, текст вопроса для лога |
| `stores.py` | Кэш feedback, фиксы ссылок `/fix` |
| `admin_access.py` | Кто считается администратором для служебных команд |
| `help_text.py` | Текст `/help` (ru/en, для админа и участника) |
| `ephemeral.py` | Автоудаление пары «команда + ответ» в группах |
| `review_mention.py` | @ревьюер в конце ответа в группах (`REPLY_REVIEW_MENTION`) |
| `telegram_log_mirror.py` | Зеркало в служебный чат (ответы, индексация, git) |
| `ops_notify.py` | Уведомления: старт, ошибки, перезапуски |
| `git_autopull.py` | Фоновый `git pull` (`GIT_AUTOPULL_*`) |
| `reply_access.py` | Проверка `getChatMember` — может ли бот писать в чат/тему |
| `panel_login.py` | Одноразовые коды входа в веб-панель |
| `constants.py` | Константы, пути к локальным JSON в `.cache/` |
| `i18n.py` | Язык ответа (ru/en), строки интерфейса |

## Модули `app/`

| Модуль | Роль |
|--------|------|
| `config.py` | Загрузка настроек из `.env` |
| `ru_layer.py` | Расширение русских запросов английскими ключевыми словами |
| `wiki_index.py`, `web_wiki_index.py` | Индекс страниц вики |
| `web_panel.py` | Встроенная веб-панель администратора |
| `error_codes_catalog.py` | Каталог кодов ошибок (scraping + кэш) |
| `resource_limits.py` | Лимит памяти (Linux/macOS `RLIMIT_AS`) |

## Данные и кэш

| Путь | Содержимое |
|------|-----------|
| `data/manual_qa.json` | Ручные Q&A (команды `/qaadd`, `/qalist`, `/qadel`) |
| `data/bad_answers.json` | Ошибочные ответы, помеченные через веб-панель |
| `.cache/` | Индекс вики, user context, recent replies, сторы — **не коммитится** |
| `logs/bot.log` | Ротируемый лог решений бота |
| `sitemap.xml` | Снимок карты сайта вики (для справки; рабочий URL — `WIKI_SITEMAP_URL`) |
