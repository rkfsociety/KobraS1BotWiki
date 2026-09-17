#!/usr/bin/env bash
# Обновление production и проверка запуска systemd-сервиса.
set -euo pipefail

EXPECTED_USER="anycubicwikibot"
SERVICE="kobras1botwiki.service"
BACKUP_SERVICE="kobras1botwiki-db-backup.service"
BACKUP_TIMER="kobras1botwiki-db-backup.timer"
RUNTIME_BACKUP_FILES=(
    "data/chat.sqlite3"
    "data/chat.sqlite3-wal"
    "data/chat.sqlite3-shm"
    "data/manual_qa.json"
    "data/missed_questions.json"
    "data/bad_answers.json"
    ".cache/recent_replies.json"
    ".cache/bot_stats.json"
    ".cache/admin_activity.json"
    ".cache/moderation.json"
    ".cache/clarify_pending.json"
    ".cache/answer_context.json"
    ".cache/feedback.json"
    ".cache/fixes.json"
    ".cache/user_ctx.json"
    ".cache/panel_sessions.json"
)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
    echo "[ERROR] Запускайте deploy только под пользователем $EXPECTED_USER" >&2
    exit 1
fi

cd "$REPO_DIR"

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "master" ]]; then
    echo "[ERROR] Deploy разрешён только из ветки master (сейчас: $current_branch)" >&2
    exit 1
fi

git fetch origin master
local_commit="$(git rev-parse HEAD)"
remote_commit="$(git rev-parse refs/remotes/origin/master)"
non_data_changes=""
while IFS= read -r local_only_commit; do
    [[ -z "$local_only_commit" ]] && continue
    commit_files="$(git show --format= --name-only "$local_only_commit")"
    commit_non_data="$(printf '%s\n' "$commit_files" | grep -vE '^$|^data/' || true)"
    if [[ -n "$commit_non_data" ]]; then
        non_data_changes+="$local_only_commit:\n$commit_non_data\n"
    fi
done < <(git rev-list "$remote_commit..$local_commit")
tracked_changes="$(git status --porcelain --untracked-files=no | grep -vE '^[ MARC?]{1,2} data/' || true)"
if [[ -n "$non_data_changes" || -n "$tracked_changes" ]]; then
    echo "[ERROR] Перед deploy обнаружены изменения вне разрешённой data-синхронизации:" >&2
    [[ -n "$non_data_changes" ]] && echo "$non_data_changes" >&2
    [[ -n "$tracked_changes" ]] && echo "$tracked_changes" >&2
    exit 1
fi

backup_stamp="$(date -u +%Y%m%d-%H%M%S)"
runtime_backup="$REPO_DIR/.cache/deploy-backups/$backup_stamp"
mkdir -p "$runtime_backup"
service_stopped=0
restore_service_on_exit() {
    if [[ "$service_stopped" == 1 ]]; then
        sudo systemctl start "$SERVICE" >/dev/null 2>&1 || true
    fi
}
trap restore_service_on_exit EXIT

sudo systemctl stop "$SERVICE"
service_stopped=1
for relative in "${RUNTIME_BACKUP_FILES[@]}"; do
    source_path="$REPO_DIR/$relative"
    if [[ -f "$source_path" ]]; then
        mkdir -p "$runtime_backup/$(dirname "$relative")"
        cp -a -- "$source_path" "$runtime_backup/$relative"
    fi
done
echo "[OK] Runtime backup: $runtime_backup"

if [[ "$local_commit" != "$remote_commit" ]]; then
    git reset --hard "$remote_commit"
fi

for relative in "${RUNTIME_BACKUP_FILES[@]}"; do
    saved_path="$runtime_backup/$relative"
    if [[ -f "$saved_path" ]]; then
        mkdir -p "$REPO_DIR/$(dirname "$relative")"
        cp -a -- "$saved_path" "$REPO_DIR/$relative"
    fi
done

python_bin="$REPO_DIR/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
    python_bin="python3"
fi
"$python_bin" "$REPO_DIR/scripts/migrate_legacy_data.py"
echo "[OK] Код обновлён до $remote_commit"

sudo systemctl restart "$SERVICE"
service_stopped=0

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
if [[ ! "$main_pid" =~ ^[1-9][0-9]*$ ]]; then
    echo "[ERROR] $SERVICE active, но MainPID некорректен: $main_pid" >&2
    systemctl status "$SERVICE" --no-pager || true
    exit 1
fi
exec_status="$(systemctl show -p ExecMainStatus --value "$SERVICE")"
if [[ "$exec_status" != "0" ]]; then
    echo "[ERROR] $SERVICE active, но ExecMainStatus=$exec_status" >&2
    systemctl status "$SERVICE" --no-pager || true
    journalctl -u "$SERVICE" -n 40 --no-pager || true
    exit 1
fi
echo "[OK] $SERVICE active (MainPID=$main_pid)"

"$python_bin" "$REPO_DIR/scripts/verify_runtime_storage.py"

# После успешной миграции runtime-state больше не зависит от tracked JSON.
git checkout -- data/

sudo install -o root -g root -m 0644 \
    "$REPO_DIR/deploy/$BACKUP_SERVICE" \
    "/etc/systemd/system/$BACKUP_SERVICE"
sudo install -o root -g root -m 0644 \
    "$REPO_DIR/deploy/$BACKUP_TIMER" \
    "/etc/systemd/system/$BACKUP_TIMER"
sudo systemctl daemon-reload
sudo systemctl enable --now "$BACKUP_TIMER"
sudo systemctl start "$BACKUP_SERVICE"

if ! systemctl is-enabled --quiet "$BACKUP_TIMER"; then
    echo "[ERROR] $BACKUP_TIMER не включён" >&2
    systemctl status "$BACKUP_TIMER" --no-pager || true
    exit 1
fi
echo "[OK] $BACKUP_TIMER enabled; первичный backup создан"
