"""HTTP-слой Telegram Mini App для администраторов одной группы."""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from typing import Any

from app.bot.miniapp_access import is_group_admin
from app.bot.miniapp_auth import MiniAppAuthError, validate_init_data
from app.bot.missed_questions import load_missed_questions


class MiniAppAccessError(PermissionError):
    """Пользователь не имеет прав администратора группы."""


def render_miniapp() -> bytes:
    """Возвращает мобильную оболочку Mini App без чувствительных данных."""
    body = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>KobraS1Bot</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body>
  <main id="app"><p>Загрузка приложения…</p></main>
  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) tg.ready();
    const root = document.getElementById('app');
    if (!tg || !tg.initData) {
      root.innerHTML = '<p>Откройте приложение через Telegram.</p>';
    } else {
      fetch('/api/app/session', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({init_data: tg.initData})
      }).then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Не удалось войти');
        sessionStorage.setItem('kobra_app_session', data.session);
        root.innerHTML = '<h1>Панель администратора</h1><p>Сессия подтверждена.</p>';
      }).catch((error) => {
        root.innerHTML = '<p>' + escapeHtml(error.message) + '</p>';
      });
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    }
  </script>
</body>
</html>
"""
    return body.encode("utf-8")


def _json_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _session_store(state: Any) -> dict[str, dict[str, Any]]:
    sessions = getattr(state, "miniapp_sessions", None)
    if sessions is None:
        sessions = {}
        state.miniapp_sessions = sessions
    return sessions


def create_miniapp_session(state: Any, init_data: str) -> tuple[int, dict[str, Any]]:
    """Проверяет Telegram initData и создаёт короткую админскую сессию."""
    try:
        verified = validate_init_data(
            init_data,
            str(getattr(state.settings, "telegram_bot_token", "")),
            max_age_seconds=86_400,
        )
    except MiniAppAuthError:
        return 401, {"error": "Сессия Telegram недействительна или устарела."}

    user = verified["user"]
    user_id = int(user["id"])
    application = state.application
    if application is None:
        return 503, {"error": "Бот ещё не готов."}
    application.bot_data.setdefault("settings", state.settings)
    if not asyncio.run(is_group_admin(application, user_id)):
        return 403, {"error": "Доступ только для администраторов группы."}

    token = secrets.token_urlsafe(32)
    ttl = min(max(300, int(getattr(state.settings, "panel_session_ttl_seconds", 1800))), 3600)
    with state.lock:
        sessions = _session_store(state)
        now = time.time()
        for old_token, session in list(sessions.items()):
            if float(session.get("exp", 0)) <= now:
                sessions.pop(old_token, None)
        sessions[token] = {"exp": now + ttl, "user": user, "role": "admin"}
    return 200, {"session": token, "user": user, "role": "admin", "capabilities": {"admin": True}}


def _get_session(state: Any, authorization: str) -> dict[str, Any] | None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    with state.lock:
        session = _session_store(state).get(token)
        if not session:
            return None
        if float(session.get("exp", 0)) <= time.time():
            _session_store(state).pop(token, None)
            return None
        return dict(session)


def dashboard_payload(state: Any, authorization: str) -> tuple[int, dict[str, Any]]:
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"error": "Сессия Mini App отсутствует или истекла."}
    bot_data = state.application.bot_data if state.application else {}
    wiki = bot_data.get("wiki_index")
    return 200, {
        "role": session["role"],
        "user": session["user"],
        "stats": {
            "wiki_pages": int(getattr(wiki, "doc_count", 0) if wiki is not None else 0),
            "total_answers": int((bot_data.get("bot_stats") or {}).get("total_answers", 0)),
            "manual_answers": len(bot_data.get("manual_qa_entries") or []),
            "missed_questions": len(load_missed_questions()),
            "fixes": len(bot_data.get("fix_store") or {}),
            "error_codes": len(bot_data.get("error_codes_catalog") or {}),
        },
    }


def missed_payload(state: Any, authorization: str) -> tuple[int, dict[str, Any]]:
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"error": "Сессия Mini App отсутствует или истекла."}
    entries = load_missed_questions()
    return 200, {"role": session["role"], "items": entries}
