# Эксплуатация

## Запуск и остановка

| Команда | Платформа |
|---------|----------|
| `python -m app.bot` | Любая (foreground) |
| `deploy\start-bot.cmd` / `stop-bot.cmd` / `restart-bot.cmd` | Windows |
| `./deploy/start-bot.sh` / `./deploy/stop-bot.sh` / `./deploy/restart-bot.sh` | Linux/macOS |

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

## Git и `/update`

Команда `/update` выполняет `git fetch` + синхронизацию от имени пользователя процесса бота.

**Ошибка прав** (`insufficient permission for adding an object`):  
Возникает, если каталог `.git/objects` создавался от root. Исправление:
```bash
chown -R user:user /путь/к/KobraS1BotWiki
```

**Автообновление**: `GIT_AUTOPULL_ENABLED=1` — периодический `git pull` без ручного `/update`.

## Тесты

```bash
pip install pytest pytest-cov
python -m pytest tests/ -v
```

CI (`.github/workflows/ci.yml`): `ruff` (линтер), `bandit` (безопасность), `pip-audit` (уязвимости в зависимостях), pytest.
