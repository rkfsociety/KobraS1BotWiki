#!/bin/bash
# Полный перезапуск бота в screen (после /update или вручную).
set -euo pipefail

# Переходим в корень проекта (родитель deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

mkdir -p .cache
LOG=".cache/restart.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

# BOT_SCREEN_NAME из .env
if [[ -f .env ]]; then
    line=$(grep -E '^BOT_SCREEN_NAME=' .env 2>/dev/null | tail -1 || true)
    if [[ -n "$line" ]]; then
        export "$line"
    fi
fi

SCREEN_NAME="${BOT_SCREEN_NAME:-kobras1botwiki}"

log "=== restart-bot: screen=$SCREEN_NAME pwd=$(pwd) ==="

# Завершить все процессы бота
if pgrep -f '[p]ython.*-m app\.bot' >/dev/null 2>&1; then
    log "pkill python -m app.bot"
    pkill -f '[p]ython.*-m app\.bot' 2>/dev/null || true
    sleep 2
fi

# Закрыть screen по lock и по имени сессии
if [[ -f .cache/bot.lock ]]; then
    "$SCRIPT_DIR/stop-bot.sh" 2>&1 | tee -a "$LOG" || true
else
    log "lock не найден, пробуем закрыть screen $SCREEN_NAME"
fi

if command -v screen >/dev/null 2>&1; then
    for _ in 1 2 3 4 5; do
        if ! screen -list 2>/dev/null | grep -qE "[0-9]+\.${SCREEN_NAME}[[:space:]]"; then
            break
        fi
        log "screen -S $SCREEN_NAME -X quit (ожидание освобождения)"
        screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
        sleep 1
    done
fi

rm -f .cache/bot.lock

sleep 1

if ! "$SCRIPT_DIR/start-bot.sh" 2>&1 | tee -a "$LOG"; then
    log "[ERROR] start-bot.sh failed, пробуем ensure-bot.sh"
    "$SCRIPT_DIR/ensure-bot.sh" 2>&1 | tee -a "$LOG" || exit 1
fi

sleep 2

if pgrep -f '[p]ython.*-m app\.bot' >/dev/null 2>&1; then
    log "OK: процесс python -m app.bot запущен"
    exit 0
fi

log "[ERROR] после перезапуска процесс бота не найден — смотрите $LOG и screen -ls"
exit 1
