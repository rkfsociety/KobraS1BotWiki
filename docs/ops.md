# Эксплуатация

## Запуск и остановка

| Команда | Платформа |
|---------|----------|
| `python -m app.bot` | Любая (foreground) |
| `deploy\start-bot.cmd` / `stop-bot.cmd` / `restart-bot.cmd` | Windows |
| `./deploy/start-bot.sh` / `./deploy/stop-bot.sh` / `./deploy/restart-bot.sh` | Linux/macOS |
| `./deploy/update-and-restart.sh` | Production: pull + systemd restart + health check |

Если бот запущен через `deploy/ensure-bot.sh` в **screen**, вывод идёт в screen и в `logs/bot.log`, а не в `journalctl`.

## Логи

```bash
# Следить за логом в реальном времени
tail -f logs/bot.log

# С sudo от имени пользователя бота
sudo -u <пользователь_бота> tail -f /путь/к/KobraS1BotWiki/logs/bot.log
```

При `LOG_DECISIONS=true` в логе появляются строки:
- `seen chat=…` — бот увидел сообщение
- `skip … reason=…` — почему не ответил (в т.ч. `reason=conversational_chatter`)

В служебный Telegram-канал эти строки **не** попадают.

## Служебный чат

По умолчанию — канал с `OPS_NOTIFY_CHAT_ID`. Бот отправляет туда:

**Зеркало ответов** (`OPS_LOG_MIRROR_ENABLED`):
- **Ответы бота** (`bot_reply`) — вопрос, текст ответа, ссылки в чате, score/url, источник запроса (🎯 авто / 📣 упоминание / ↩️ reply / 👤 личка), модель принтера
- **Негативные реакции** (💩/👎 от админа) — карточка с вопросом и ответом для разбора
- **Старт** — компактная строка: username, число страниц вики, QA, коды ошибок
- **Индексация** — прогресс и завершение
- **Git** — `/update`, autopull, перезапуск

**Не зеркалятся**: `seen`, `skip reason=`, уточнения `clarify`, шум apscheduler/httpx.

**Отключить зеркало**: `OPS_LOG_MIRROR_ENABLED=0`  
**Сменить/выключить чат**: `OPS_NOTIFY_CHAT_ID=0`

> Чтобы реакции в группах приходили в зеркало, бот должен быть **администратором** чата.

## Меню команд Telegram

При запуске бот обновляет встроенное меню команд Telegram. Участники видят
`/start` и `/help`, а администраторы групп — также поиск, диагностику и
модерацию. Список локализован для русского и английского интерфейса Telegram;
для остальных языков используется русский вариант.

## Ежедневная статистика групп

В 00:05 по часовому поясу `Europe/Kaliningrad` бот отправляет сводку за
предыдущий день в каждый чат из `ALLOWED_CHAT_IDS`: в форумных чатах — в
тему из `DAILY_STATS_TOPIC_ID`; значение `0` означает общую тему без передачи
`message_thread_id`, в обычных группах параметр темы не используется.
Статистика запрашивается отдельно по каждому `chat_id`, поэтому сообщения
разных групп не смешиваются. Если `ALLOWED_CHAT_IDS` не задан, используется
`PANEL_ADMIN_CHAT_ID`.

## Миграция старых данных в единую SQLite

Перед первым запуском версии с единой историей остановите сервис: миграция не
должна выполняться параллельно с polling. После `git pull --ff-only` запустите
скрипт от имени `anycubicwikibot`:

```bash
sudo systemctl stop kobras1botwiki.service
cd /home/anycubicwikibot/KobraS1BotWiki
git pull --ff-only
python3 scripts/migrate_legacy_data.py
sudo systemctl start kobras1botwiki.service
```

`scripts/migrate_legacy_data.py` перед записью делает резервную копию старой
SQLite и JSON-источников в `.cache/migration-backups/`, сохраняет старые
агрегаты как baseline и импортирует доступные текстовые образцы с меткой
`legacy`. При старте новой версии все штатные JSON-state-модули импортируются
в `bot_state` общей базы до запуска polling. Исходные JSON сохраняются до
успешной проверки базы, затем deploy-скрипт может очистить их tracked-копии.

### Ежедневные резервные копии базы

Копия создаётся через SQLite Online Backup API, затем проходит
`PRAGMA integrity_check` и получает sidecar SHA-256. Хранятся последние 14 дней
в `.cache/db-backups/`.

После запуска сервис дополнительно выполняет
`scripts/verify_runtime_storage.py`: проверяет целостность базы, наличие
`chat_messages` и всех обязательных runtime namespace в `bot_state`.

При штатном запуске `./deploy/update-and-restart.sh` units устанавливаются и
таймер включается автоматически. Для ручной установки (например, при первом
развёртывании отдельно от обновления кода) используйте от имени пользователя
с правами sudo:

```bash
sudo cp deploy/kobras1botwiki-db-backup.service /etc/systemd/system/
sudo cp deploy/kobras1botwiki-db-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kobras1botwiki-db-backup.timer
sudo systemctl start kobras1botwiki-db-backup.service
systemctl list-timers kobras1botwiki-db-backup.timer
ls -l /home/anycubicwikibot/KobraS1BotWiki/.cache/db-backups/
```

Пушить рабочие данные очередей и состояния в Git больше не требуется: Git
используется только для кода и конфигурации, а резервирование рабочих данных
выполняет этот таймер.

## Git и `/update`

Команда `/update` выполняет `git fetch` + синхронизацию от имени пользователя процесса бота.

**Ошибка прав** (`insufficient permission for adding an object`):  
Возникает, если каталог `.git/objects` создавался от root. Исправление:
```bash
chown -R user:user /путь/к/KobraS1BotWiki
```

**Автообновление**: `GIT_AUTOPULL_ENABLED=1` — периодический `git pull` без ручного `/update`.

## Тесты

Для локальной проверки на Windows используй отдельное окружение и UTF-8:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install pytest pytest-cov ruff
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

Полный последовательный прогон с coverage:

```powershell
ruff check app tests scripts
python -X utf8 -m pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=xml --basetemp=.pytest-tmp
```

Не запускай длинные проверки параллельно через Codex. На Windows не импортируй
без проверки `fcntl` и не используй `os.kill(pid, 0)` для проверки живого PID;
для atomic-write при конкурентных потоках нужна сериализация `replace()` и
ограниченный retry для временного `PermissionError`. Подробности — в
`.codex/windows-test-compatibility.md`.

Последняя проверенная Windows-конфигурация: `913 passed`, Ruff без ошибок,
coverage `64%`.

CI (`.github/workflows/ci.yml`): `ruff` (линтер), `bandit` (безопасность), `pip-audit` (уязвимости в зависимостях), pytest.
