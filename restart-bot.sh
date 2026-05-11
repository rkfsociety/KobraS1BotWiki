#!/bin/bash

set -e

# Переходим в директорию скрипта
cd "$(dirname "$0")"

echo "Restarting bot..."

# Останавливаем бота
./stop-bot.sh

# Небольшая пауза
sleep 1

# Запускаем бота
./start-bot.sh

echo "Done."
