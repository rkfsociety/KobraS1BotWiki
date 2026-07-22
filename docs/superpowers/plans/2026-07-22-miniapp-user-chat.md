# Пользовательский чат Mini App Implementation Plan

> **Для исполнителя:** перед началом использовать `superpowers:subagent-driven-development` или `superpowers:executing-plans` и выполнять шаги по порядку. Каждый этап заканчивается проверкой.

**Цель:** заменить тестовую форму пользовательского режима на персональный SQLite-чат с сохранением истории, ответами из базы бота и серверной защитой от спама.

**Архитектура:** отдельный модуль `app/bot/chat_store.py` отвечает только за SQLite-схему, историю и rate limit. `app/web_miniapp.py` использует его через функции API: идентификатор пользователя берётся из Bearer-сессии, а не из запроса. HTML/JavaScript Mini App отображает историю и отправляет новые вопросы через JSON-совместимые HTTP endpoint.

**Технологии:** Python 3.12, стандартный `sqlite3`, существующий HTTP-сервер панели, Telegram Mini App WebApp API, pytest, ruff.

## Общие ограничения

- Приложение обслуживает одну настроенную Telegram-группу.
- История разделяется по Telegram ID пользователя.
- Обычный пользователь не получает админские endpoint; админский предпросмотр использует уже проверенную admin-сессию.
- При создании Mini App-сессии обычный участник получает роль `user` после проверки членства в настроенной группе; администратор получает роль `admin` после проверки статуса `OWNER`/`ADMINISTRATOR`.
- `dashboard`, `missed`, `answer` и `dismiss` доступны только роли `admin`; `chat/history` и `chat/message` доступны роли `user` и `admin`.
- SQLite-файл находится в `data/`; токены и `.env` не добавляются в git.
- Лимиты проверяются на сервере: 1 сообщение за 3 секунды и 20 сообщений за 10 минут.
- Вопрос ограничен 2–2000 символами; история пользователя ограничена последними 500 сообщениями.
- После каждого изменения файлов запускаются целевые тесты; перед завершением — полный pytest и ruff по изменённым Python-файлам.

---

### Задача 1: SQLite-хранилище истории и лимитов

**Файлы:**
- Создать: `app/bot/chat_store.py`
- Создать: `tests/test_chat_store.py`

**Интерфейсы:**
- `ChatStore(path: Path)` — открывает SQLite-файл, создаёт каталог, включает WAL и создаёт таблицы.
- `ChatMessage` — dataclass с `id`, `user_id`, `role`, `text`, `source`, `created_at`, `reply_to_id`.
- `ChatStore.add_message(user_id: int, role: str, text: str, source: str, reply_to_id: int | None = None) -> ChatMessage`.
- `ChatStore.list_messages(user_id: int, limit: int = 50, before_id: int | None = None) -> list[ChatMessage]`.
- `ChatStore.allow_request(user_id: int, now: float | None = None) -> tuple[bool, int]`; при разрешении атомарно записывает событие, при отказе возвращает секунды до повтора.
- `ChatStore.find_recent_duplicate(user_id: int, text: str, now: float | None = None) -> tuple[ChatMessage, ChatMessage] | None`.
- `ChatStore.prune_user_history(user_id: int, keep: int = 500) -> None`.

- [ ] **Шаг 1: написать падающие тесты** на создание таблиц, изоляцию пользователей, порядок и пагинацию сообщений, лимит 3 секунды, лимит 20 сообщений за 10 минут и удаление истории старше 500 сообщений.
- [ ] **Шаг 2: запустить тесты и убедиться, что они падают**.

  Запуск: `python -m pytest tests/test_chat_store.py -q --basetemp=C:\Temp\kobra-pytest`

  Ожидание: FAIL из-за отсутствующего `app.bot.chat_store`.

- [ ] **Шаг 3: реализовать минимальное SQLite-хранилище** с параметризованными SQL-запросами, `sqlite3.Row`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, индексами `(user_id, id)` и `(user_id, created_at)`, а также транзакцией для rate limit.
- [ ] **Шаг 4: запустить тесты и убедиться, что они проходят**.
- [ ] **Шаг 5: закоммитить**:

  `git add app/bot/chat_store.py tests/test_chat_store.py && git commit -m "Добавить SQLite-хранилище чата"`

### Задача 2: Серверные endpoint истории и сообщения

**Файлы:**
- Изменить: `app/web_miniapp.py`
- Изменить: `app/web_panel.py`
- Изменить: `tests/test_web_miniapp.py`

**Интерфейсы:**
- `chat_history_payload(state: Any, authorization: str, limit: int, before_id: int | None) -> tuple[int, dict[str, Any]]`.
- `chat_message_payload(state: Any, authorization: str, text: str) -> tuple[int, dict[str, Any]]`.
- В `_PanelState` добавить один `ChatStore`, созданный на пути `data/chat.sqlite3` через существующий путь проекта.

- [ ] **Шаг 1: добавить падающие интеграционные тесты** на `GET /api/app/chat/history`, получение manual-ответа, получение wiki-ответа, запись неизвестного вопроса, собственную историю двух пользователей, `401` без Bearer-сессии и `429` при превышении лимита.
- [ ] **Шаг 2: запустить новые тесты и проверить ожидаемый RED**.
- [ ] **Шаг 3: подключить `ChatStore` к состоянию веб-панели** и добавить маршруты:

  ```python
  if path == "/api/app/chat/history":
      status, payload = chat_history_payload(state, authorization, limit, before_id)
  if path == "/api/app/chat/message":
      status, payload = chat_message_payload(state, authorization, form.get("text", ""))
  ```

  `chat_message_payload` должен:
  1. получить `session["user"]["id"]` через `_get_session`;
  2. проверить длину текста;
  3. проверить недавний дубликат;
  4. вызвать `allow_request` до поиска;
  5. сохранить сообщение пользователя;
  6. проверить `find_manual_qa_answer`, затем `wiki_index.search(top_k=1)` и `MIN_SCORE`;
  7. неизвестный вопрос передать в `add_missed_question`;
  8. сохранить ответ бота с `source` и `reply_to_id`;
  9. вернуть пару сообщений и метаданные лимита.

  `create_miniapp_session` должен различать роли: сначала проверить, что пользователь состоит в настроенной группе, затем определить админа через существующую `is_group_admin`. Админские payload-функции обязаны отклонять сессию роли `user` ответом `403`.

- [ ] **Шаг 4: запустить интеграционные тесты и проверить GREEN**.
- [ ] **Шаг 5: закоммитить**:

  `git add app/web_miniapp.py app/web_panel.py tests/test_web_miniapp.py && git commit -m "Добавить API персонального чата Mini App"`

### Задача 3: Интерфейс ленты чата

**Файлы:**
- Изменить: `app/web_miniapp.py`
- Изменить: `tests/test_web_miniapp.py`

**Интерфейсы JavaScript:**
- `renderUserMode()` — создаёт экран чата и загружает историю.
- `loadChatHistory(beforeId)` — добавляет историю пользователя без очистки текущей ленты.
- `sendChatMessage(event)` — отправляет вопрос, блокирует кнопку на время запроса и добавляет пару сообщений.
- `appendChatMessage(message)` — безопасно экранирует текст и рисует пузырь сообщения.

- [ ] **Шаг 1: добавить падающие проверки HTML** на `chat-history`, `sendChatMessage`, `loadChatHistory`, кнопку старых сообщений, `aria-label` поля ввода и отсутствие прежней отдельной формы `askQuestion`.
- [ ] **Шаг 2: запустить тесты и увидеть RED**.
- [ ] **Шаг 3: реализовать адаптивную ленту**: `overflow-y:auto`, `min-height:0`, нижняя форма ввода, сообщения пользователя/бота, состояние загрузки и обработка `429` через `retry_after`.
- [ ] **Шаг 4: запустить целевые тесты и проверить GREEN**.
- [ ] **Шаг 5: закоммитить**:

  `git add app/web_miniapp.py tests/test_web_miniapp.py && git commit -m "Сделать пользовательский режим чатом"`

### Задача 4: Конфигурация, очистка и финальная проверка

**Файлы:**
- Изменить: `docs/web-panel.md`
- Изменить: `.gitignore` при необходимости
- Создать/изменить: `tests/test_chat_store.py` только если нужна проверка миграции

- [ ] **Шаг 1: добавить документацию** о `data/chat.sqlite3`, персональной истории, лимитах и том, что админский режим пользователя является предпросмотром.
- [ ] **Шаг 2: убедиться, что SQLite-файл не попадает в git**; добавить точечное правило `data/chat.sqlite3*` только если текущие правила этого не обеспечивают.
- [ ] **Шаг 3: прогнать проверки**:

  `python -m pytest -q --basetemp=C:\Temp\kobra-pytest`

  `ruff check app/bot/chat_store.py app/web_miniapp.py app/web_panel.py tests/test_chat_store.py tests/test_web_miniapp.py`

- [ ] **Шаг 4: проверить** `git diff --check` и отсутствие `.env`, токенов и SQLite-файлов в staged diff.
- [ ] **Шаг 5: создать итоговый коммит**:

  `git add docs/web-panel.md .gitignore && git commit -m "Документировать пользовательский чат Mini App"`

## Контрольные точки

- После задачи 1: SQLite-слой тестируется независимо от HTTP.
- После задачи 2: API возвращает персональные сообщения и корректно ограничивает спам.
- После задачи 3: Mini App открывает полноценный чат и не показывает чужую историю.
- После задачи 4: полный набор тестов проходит, рабочее дерево чистое.
