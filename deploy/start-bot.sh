#!/bin/bash

set -e

# Переходим в корень проекта (родитель deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# BOT_SCREEN_NAME из .env (напр. 511.bot) или из окружения
if [[ -f .env ]]; then
    line=$(grep -E '^BOT_SCREEN_NAME=' .env 2>/dev/null | tail -1 || true)
    if [[ -n "$line" ]]; then
        export "$line"
    fi
fi
SCREEN_NAME="${BOT_SCREEN_NAME:-kobras1botwiki}"

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    echo "[ERROR] Не найден .env в папке проекта: $(pwd)"
    echo "Скопируйте .env.example в .env и заполните TELEGRAM_BOT_TOKEN."
    exit 1
fi

if ! command -v screen >/dev/null 2>&1; then
    echo "[ERROR] Не найдена команда screen. Установите, например: sudo apt install screen"
    exit 1
fi

echo "Starting bot in screen session '$SCREEN_NAME'..."

# Интерпретатор: локальное venv, если есть
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi
if ! "$PYTHON" -c "import dotenv" 2>/dev/null; then
    echo "[ERROR] Не установлен пакет python-dotenv (или не те зависимости)."
    echo "Установите зависимости в том же Python, что запускает бота, например:"
    echo "  $PYTHON -m pip install -r requirements.txt"
    echo "Или создайте venv в каталоге проекта:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if screen -list 2>/dev/null | grep -qE "[0-9]+\.${SCREEN_NAME}[[:space:]]"; then
    echo "[ERROR] Сессия screen '$SCREEN_NAME' уже существует."
    echo "Подключиться к логам: screen -r $SCREEN_NAME"
    echo "Если вы root, а бот от другого пользователя (systemd User=): sudo -u <пользователь> screen -r $SCREEN_NAME"
    echo "Остановить бота: ./deploy/stop-bot.sh"
    exit 1
fi

mkdir -p .cache

# Отсоединённая сессия: можно закрывать PuTTY, бот продолжит работу
screen -dmS "$SCREEN_NAME" env PYTHONUNBUFFERED=1 "$PYTHON" -m app.bot

# Для stop-bot.sh: помечаем, что процесс в screen
echo "screen:${SCREEN_NAME}" > ".cache/bot.lock"

echo "Started (detached). Сессия: $SCREEN_NAME"
echo "Подключиться к выводу в терминале: screen -r $SCREEN_NAME"
echo "Если вы root, а screen у другого пользователя: sudo -u <пользователь> screen -r $SCREEN_NAME"
echo "Отключиться от screen без остановки бота: Ctrl+A, затем D"
echo "Остановить бота: ./deploy/stop-bot.sh"
echo "Проверка «жив ли» и автозапуск: ./deploy/ensure-bot.sh (удобно в cron)"
echo "Done."
