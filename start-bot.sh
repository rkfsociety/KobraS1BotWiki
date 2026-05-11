#!/bin/bash

set -e

# Переходим в директорию скрипта
cd "$(dirname "$0")"

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    echo "[ERROR] Не найден .env в папке проекта: $(pwd)"
    echo "Скопируйте .env.example в .env и заполните TELEGRAM_BOT_TOKEN."
    exit 1
fi

echo "Starting bot..."

# Создаем директорию .cache если не существует
if [ ! -d ".cache" ]; then
    mkdir -p ".cache"
fi

# Запускаем бота в фоновом режиме и сохраняем PID
PYTHONUNBUFFERED=1 python -m app.bot &
BOT_PID=$!

# Сохраняем PID в lock-файл
echo "$BOT_PID" > ".cache/bot.lock"

echo "Started bot pid=$BOT_PID"
echo "Done."
