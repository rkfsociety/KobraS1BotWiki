"""HTTP-слой Telegram Mini App для администраторов одной группы."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from typing import Any

from app.bot.miniapp_access import is_group_admin
from app.bot.miniapp_auth import MiniAppAuthError, validate_init_data
from app.bot.manual_qa import add_manual_qa_entry, load_manual_qa_store
from app.bot.missed_questions import delete_missed_question_by_text, load_missed_questions


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
  <style>
    :root { color-scheme: dark; --bg:#0b0d11; --panel:#141821; --line:#29303b; --text:#f5f7fb; --muted:#8d98aa; --amber:#f0c674; --blue:#5c9cff; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; background:radial-gradient(circle at 15% 0%,#202331 0,#0b0d11 42%); color:var(--text); font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif; }
    .miniapp-shell { width:min(100%,720px); margin:0 auto; padding:20px 16px 32px; }
    .miniapp-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; margin-bottom:20px; }
    h1,h2,p { margin:0; } h1 { font-size:25px; letter-spacing:-.02em; } h2 { font-size:14px; }
    .muted { color:var(--muted); } .eyebrow { color:var(--amber); font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
    .miniapp-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
    .miniapp-card { background:linear-gradient(145deg,#171c27,#11151d); border:1px solid var(--line); border-radius:16px; padding:15px; box-shadow:0 12px 28px #0003; }
    .miniapp-card .value { color:var(--amber); font-size:25px; font-weight:750; margin:5px 0 1px; }
    .miniapp-card--wide { grid-column:1/-1; } .miniapp-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
    button { border:0; border-radius:10px; background:var(--amber); color:#17130b; cursor:pointer; font:600 13px inherit; padding:10px 13px; }
    button.secondary { background:#263244; color:var(--text); } .error { color:#ff8d8d; }
    @media (min-width:560px) { .miniapp-grid { grid-template-columns:repeat(4,minmax(0,1fr)); } }
  </style>
</head>
<body>
  <main id="app" class="miniapp-shell"><p>Загрузка приложения…</p></main>
  <script>
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) tg.ready();
    const root = document.getElementById('app');
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    }
    function renderDashboard(data) {
      const s = data.stats || {};
      root.innerHTML = `<div class="miniapp-head"><div><div class="eyebrow">KobraS1Bot</div><h1>Панель администратора</h1><p class="muted">${escapeHtml(data.user.first_name || 'Администратор')}</p></div><div class="eyebrow">ADMIN</div></div>
        <section class="miniapp-grid">
          <article class="miniapp-card"><div class="muted">Страницы вики</div><div class="value">${s.wiki_pages || 0}</div></article>
          <article class="miniapp-card"><div class="muted">Ответы бота</div><div class="value">${s.total_answers || 0}</div></article>
          <article class="miniapp-card"><div class="muted">Ручные ответы</div><div class="value">${s.manual_answers || 0}</div></article>
          <article class="miniapp-card"><div class="muted">Вопросы без ответа</div><div class="value">${s.missed_questions || 0}</div></article>
          <article class="miniapp-card miniapp-card--wide"><h2>Очередь разбора</h2><p class="muted">Вопросы, которым нужно добавить ручной ответ или улучшить поиск.</p><div class="miniapp-actions"><button onclick="loadMissed()">Открыть вопросы</button><button class="secondary" onclick="loadDashboard()">Обновить</button></div><div id="missed" class="muted" style="margin-top:12px"></div></article>
        </section>`;
    }
    function loadDashboard() {
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/dashboard', {headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка загрузки'); renderDashboard(data); })
        .catch((error) => { root.innerHTML = '<p class="error">' + escapeHtml(error.message) + '</p>'; });
    }
    function loadMissed() {
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/missed', {headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка загрузки'); renderMissed(data.items); })
        .catch((error) => { const box = document.getElementById('missed'); if (box) box.innerHTML = '<span class="error">' + escapeHtml(error.message) + '</span>'; });
    }
    function renderMissed(items) {
      const box = document.getElementById('missed');
      if (!box) return;
      if (!items.length) { box.innerHTML = 'Очередь пуста.'; return; }
      box.innerHTML = items.map((item) => `<article class="miniapp-card" style="margin-top:10px"><p>${escapeHtml(item.text)}</p><input id="title-${item.id}" placeholder="Заголовок" style="width:100%;margin-top:9px;padding:9px;border-radius:8px;border:1px solid var(--line);background:#0d1118;color:var(--text)"><textarea id="answer-${item.id}" placeholder="Короткий ручной ответ" style="width:100%;min-height:72px;margin-top:8px;padding:9px;border-radius:8px;border:1px solid var(--line);background:#0d1118;color:var(--text)"></textarea><div class="miniapp-actions"><button onclick="submitAnswer('${item.id}')">Сохранить ответ</button><button class="secondary" onclick="dismissQuestion('${item.id}')">Отметить как оффтоп</button></div></article>`).join('');
    }
    function submitAnswer(id) {
      const token = sessionStorage.getItem('kobra_app_session');
      const body = new URLSearchParams({title: document.getElementById('title-' + id).value, answer: document.getElementById('answer-' + id).value});
      fetch('/api/app/missed/' + encodeURIComponent(id) + '/answer', {method:'POST', headers:{Authorization:'Bearer ' + token, 'Content-Type':'application/x-www-form-urlencoded'}, body})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Не удалось сохранить'); loadDashboard(); })
        .catch((error) => { const box = document.getElementById('missed'); if (box) box.innerHTML = '<span class="error">' + escapeHtml(error.message) + '</span>'; });
    }
    function dismissQuestion(id) {
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/missed/' + encodeURIComponent(id) + '/dismiss', {method:'POST', headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Не удалось удалить'); loadDashboard(); })
        .catch((error) => { const box = document.getElementById('missed'); if (box) box.innerHTML = '<span class="error">' + escapeHtml(error.message) + '</span>'; });
    }
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
        loadDashboard();
      }).catch((error) => {
        root.innerHTML = '<p class="error">' + escapeHtml(error.message) + '</p>';
      });
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
    entries = []
    for entry in load_missed_questions():
        item = dict(entry)
        item["id"] = _missed_id(item)
        entries.append(item)
    return 200, {"role": session["role"], "items": entries}


def _missed_id(entry: dict[str, Any]) -> str:
    raw = f"{entry.get('text', '')}\x00{entry.get('ts', '')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _find_missed(item_id: str) -> dict[str, Any] | None:
    for entry in load_missed_questions():
        if _missed_id(entry) == item_id:
            return entry
    return None


def answer_missed_payload(
    state: Any,
    authorization: str,
    item_id: str,
    *,
    title: str,
    answer: str,
) -> tuple[int, dict[str, Any]]:
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"ok": False, "error": "Сессия Mini App отсутствует или истекла."}
    answer = answer.strip()
    if not answer or len(answer) > 10_000:
        return 400, {"ok": False, "error": "Ответ должен содержать от 1 до 10000 символов."}
    entry = _find_missed(item_id)
    if entry is None:
        return 404, {"ok": False, "error": "Вопрос уже обработан или не найден."}

    entries = load_manual_qa_store()
    ok, message = add_manual_qa_entry(
        entries=entries,
        raw_keys=[str(entry.get("text", ""))],
        answer=answer,
        title=title.strip()[:200],
    )
    if not ok:
        return 400, {"ok": False, "error": message}
    deleted, delete_message = delete_missed_question_by_text(text=str(entry.get("text", "")))
    if not deleted:
        return 500, {"ok": False, "error": f"Ответ сохранён, но вопрос не удалён: {delete_message}"}
    if state.application is not None:
        state.application.bot_data["manual_qa_entries"] = entries
    return 200, {"ok": True, "message": "Ручной ответ сохранён."}


def dismiss_missed_payload(state: Any, authorization: str, item_id: str) -> tuple[int, dict[str, Any]]:
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"ok": False, "error": "Сессия Mini App отсутствует или истекла."}
    entry = _find_missed(item_id)
    if entry is None:
        return 404, {"ok": False, "error": "Вопрос уже обработан или не найден."}
    ok, message = delete_missed_question_by_text(text=str(entry.get("text", "")))
    return (200 if ok else 500), {"ok": ok, "message": message} if ok else {"ok": False, "error": message}
