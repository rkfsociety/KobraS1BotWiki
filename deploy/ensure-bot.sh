#!/bin/bash
# Проверка: запущен ли бот; если нет — очистка screen/lock и ./deploy/start-bot.sh
#
# Пример cron (каждые 5 минут):
#   */5 * * * * cd /home/USER/KobraS1BotWiki && ./deploy/ensure-bot.sh >>.cache/ensure.log 2>&1
#
# Имя сессии screen как у start-bot.sh: переменная BOT_SCREEN_NAME (по умолчанию kobras1botwiki).

set -e

# Переходим в корень проекта (родитель deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

if [[ -f .env ]]; then
    line=$(grep -E '^BOT_SCREEN_NAME=' .env 2>/dev/null | tail -1 || true)
    if [[ -n "$line" ]]; then
        export "$line"
    fi
fi

mkdir -p .cache
exec 9>>.cache/bot.ensure.lock
if ! flock -n 9; then
    echo "ensure-bot: другой экземпляр уже выполняется, выход."
    exit 0
fi

DEFAULT_SCREEN="${BOT_SCREEN_NAME:-kobras1botwiki}"
LOCK_FILE=".cache/bot.lock"
LOCK_LINE=""
if [[ -f "$LOCK_FILE" ]]; then
    LOCK_LINE=$(tr -d '\r\n' <"$LOCK_FILE")
fi

SESSION="$DEFAULT_SCREEN"
if [[ "$LOCK_LINE" == screen:* ]]; then
    SESSION="${LOCK_LINE#screen:}"
fi

session_exists() {
    local name="$1"
    screen -list 2>/dev/null | grep -qE "[0-9]+\.${name}[[:space:]]"
}

bot_python_running() {
    pgrep -f '[p]ython.*-m app\.bot' >/dev/null 2>&1
}

if bot_python_running; then
    echo "ensure-bot: OK (процесс python -m app.bot уже есть)."
    exit 0
fi

# Старый формат lock: только PID фонового процесса
if [[ "$LOCK_LINE" =~ ^[0-9]+$ ]] && kill -0 "$LOCK_LINE" 2>/dev/null; then
    echo "ensure-bot: OK (по $LOCK_FILE процесс $LOCK_LINE ещё жив)."
    exit 0
fi

echo "ensure-bot: бот не отвечает — останавливаю остатки screen и запускаю заново..."

if [[ "$LOCK_LINE" == screen:* ]]; then
    screen -S "${LOCK_LINE#screen:}" -X quit 2>/dev/null || true
fi
if session_exists "$SESSION"; then
    screen -S "$SESSION" -X quit 2>/dev/null || true
fi

rm -f "$LOCK_FILE"

"$SCRIPT_DIR/start-bot.sh"
echo "ensure-bot: запуск выполнен."
