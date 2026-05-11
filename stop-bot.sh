#!/bin/bash

set -e

# Переходим в директорию скрипта
cd "$(dirname "$0")"

LOCK_FILE=".cache/bot.lock"

# Проверка наличия lock-файла
if [ ! -f "$LOCK_FILE" ]; then
    echo "Lock file not found: $LOCK_FILE"
    echo "Если бот всё ещё запущен, завершите его вручную (kill python)."
    exit 0
fi

# Читаем PID из lock-файла
BOT_PID=$(cat "$LOCK_FILE")

echo "Stopping bot pid=$BOT_PID ..."

# Проверяем, запущен ли процесс с таким PID
if kill -0 "$BOT_PID" 2>/dev/null; then
    # Отправляем сигнал завершения процессу и всем его дочерним процессам
    kill -TERM "$BOT_PID" 2>/dev/null || true
    
    # Ждем немного для корректного завершения
    sleep 1
    
    # Если процесс всё ещё активен, убиваем принудительно
    if kill -0 "$BOT_PID" 2>/dev/null; then
        kill -9 "$BOT_PID" 2>/dev/null || true
    fi
    
    echo "Bot process terminated."
else
    echo "Process with pid=$BOT_PID is not running."
fi

# Удаляем lock-файл
rm -f "$LOCK_FILE"

echo "Done."
