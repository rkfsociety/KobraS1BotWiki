#!/bin/bash

set -e

# Переходим в корень проекта (родитель deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

LOCK_FILE=".cache/bot.lock"

# Проверка наличия lock-файла
if [ ! -f "$LOCK_FILE" ]; then
    echo "Lock file not found: $LOCK_FILE"
    echo "Если бот всё ещё запущен, завершите его вручную (screen -ls, ./deploy/stop-bot.sh после правки lock, или kill)."
    exit 0
fi

LOCK_RAW=$(tr -d '\r\n' < "$LOCK_FILE")

# Новый формат: screen:имя_сессии
if [[ "$LOCK_RAW" == screen:* ]]; then
    SESSION="${LOCK_RAW#screen:}"
    echo "Stopping screen session '$SESSION' ..."
    if command -v screen >/dev/null 2>&1; then
        screen -S "$SESSION" -X quit 2>/dev/null || true
    fi
    rm -f "$LOCK_FILE"
    echo "Done."
    exit 0
fi

# Старый формат: только PID процесса
BOT_PID="$LOCK_RAW"

echo "Stopping bot pid=$BOT_PID ..."

if kill -0 "$BOT_PID" 2>/dev/null; then
    kill -TERM "$BOT_PID" 2>/dev/null || true
    sleep 1
    if kill -0 "$BOT_PID" 2>/dev/null; then
        kill -9 "$BOT_PID" 2>/dev/null || true
    fi
    echo "Bot process terminated."
else
    echo "Process with pid=$BOT_PID is not running."
fi

rm -f "$LOCK_FILE"
echo "Done."
