#!/usr/bin/env bash
# Обновление production и проверка запуска systemd-сервиса.
set -euo pipefail

EXPECTED_USER="anycubicwikibot"
SERVICE="kobras1botwiki.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
    echo "[ERROR] Запускайте deploy только под пользователем $EXPECTED_USER" >&2
    exit 1
fi

cd "$REPO_DIR"

# Живой бот может коммитить data-файлы сам; не смешиваем их с обновлением кода.
git checkout -- data/
git pull --ff-only

sudo systemctl restart "$SERVICE"

for _ in 1 2 3; do
    sleep 2
    if ! systemctl is-active --quiet "$SERVICE"; then
        echo "[ERROR] $SERVICE не запустился или завершился после restart" >&2
        systemctl status "$SERVICE" --no-pager || true
        journalctl -u "$SERVICE" -n 40 --no-pager || true
        exit 1
    fi
done

service_user="$(systemctl show -p User --value "$SERVICE")"
if [[ "$service_user" != "$EXPECTED_USER" ]]; then
    echo "[ERROR] $SERVICE запущен не под $EXPECTED_USER (User=$service_user)" >&2
    systemctl status "$SERVICE" --no-pager || true
    exit 1
fi

main_pid="$(systemctl show -p MainPID --value "$SERVICE")"
echo "[OK] $SERVICE active (MainPID=$main_pid)"
