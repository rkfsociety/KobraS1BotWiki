"""HTTP-слой Telegram Mini App для администраторов одной группы."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from typing import Any

from app.bot.miniapp_access import is_group_admin, is_group_member
from app.bot.miniapp_auth import MiniAppAuthError, validate_init_data
from app.bot.manual_qa import add_manual_qa_entry, find_manual_qa_answer, load_manual_qa_store
from app.bot.missed_questions import add_missed_question, delete_missed_question_by_text, load_missed_questions


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
    .miniapp-head__actions { display:flex; flex-direction:column; align-items:flex-end; gap:8px; }
    h1,h2,p { margin:0; } h1 { font-size:25px; letter-spacing:-.02em; } h2 { font-size:14px; }
    .muted { color:var(--muted); } .eyebrow { color:var(--amber); font-size:11px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
    .miniapp-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
    .miniapp-card { background:linear-gradient(145deg,#171c27,#11151d); border:1px solid var(--line); border-radius:16px; padding:15px; box-shadow:0 12px 28px #0003; }
    .miniapp-card .value { color:var(--amber); font-size:25px; font-weight:750; margin:5px 0 1px; }
    .miniapp-card--wide { grid-column:1/-1; } .miniapp-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
    button { border:0; border-radius:10px; background:var(--amber); color:#17130b; cursor:pointer; font:600 13px inherit; padding:10px 13px; }
    button.secondary { background:#263244; color:var(--text); } .error { color:#ff8d8d; }
    .chat-card { display:flex; flex-direction:column; min-height:60vh; }
    #chat-history { display:flex; flex:1; flex-direction:column; gap:10px; min-height:0; max-height:55vh; overflow-x:hidden; overflow-y:auto; padding:4px 2px 12px; }
    .chat-load-more { align-self:center; margin-bottom:8px; }
    .chat-message { display:flex; max-width:88%; }
    .chat-message--user { align-self:flex-end; }
    .chat-message--bot { align-self:flex-start; }
    .chat-bubble { border-radius:14px; padding:10px 12px; white-space:pre-wrap; overflow-wrap:anywhere; }
    .chat-message--user .chat-bubble { background:#315d9b; }
    .chat-message--bot .chat-bubble { background:#252d3a; }
    .chat-bubble a { color:var(--blue); }
    .chat-form { display:flex; gap:8px; margin-top:10px; align-items:flex-end; }
    #chat-input { flex:1; min-width:0; min-height:48px; max-height:140px; padding:10px; border:1px solid var(--line); border-radius:10px; background:#0d1118; color:var(--text); font:inherit; resize:vertical; }
    .chat-status { min-height:20px; margin-top:8px; }
    .miniapp-error { display:grid; place-items:center; min-height:60vh; padding:24px; text-align:center; }
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
      root.innerHTML = `<div class="miniapp-head"><div><div class="eyebrow">KobraS1Bot</div><h1>Панель администратора</h1><p class="muted">${escapeHtml(data.user.first_name || 'Администратор')}</p></div><div class="miniapp-head__actions"><div class="eyebrow">ADMIN</div><button class="secondary" onclick="setUserMode()">Режим пользователя</button></div></div>
        <section class="miniapp-grid">
          <article class="miniapp-card"><div class="muted">Страницы вики</div><div class="value">${s.wiki_pages || 0}</div></article>
          <article class="miniapp-card"><div class="muted">Ответы бота</div><div class="value">${s.total_answers || 0}</div></article>
          <article class="miniapp-card"><div class="muted">Ручные ответы</div><div class="value">${s.manual_answers || 0}</div></article>
          <article class="miniapp-card"><div class="muted">Вопросы без ответа</div><div class="value">${s.missed_questions || 0}</div></article>
          <article class="miniapp-card miniapp-card--wide"><h2>Поиск по вики</h2><form onsubmit="searchWiki(event)" class="miniapp-actions"><input id="wiki-query" placeholder="Например: первый слой" style="flex:1;min-width:180px;padding:10px;border-radius:8px;border:1px solid var(--line);background:#0d1118;color:var(--text)"><button type="submit">Найти</button></form><div id="search-results" class="muted" style="margin-top:12px"></div></article>
          <article class="miniapp-card miniapp-card--wide"><h2>Очередь разбора</h2><p class="muted">Вопросы, которым нужно добавить ручной ответ или улучшить поиск.</p><div class="miniapp-actions"><button onclick="loadMissed()">Открыть вопросы</button><button class="secondary" onclick="loadDashboard()">Обновить</button></div><div id="missed" class="muted" style="margin-top:12px"></div></article>
        </section>`;
    }
    let currentSessionRole = null;
    let chatHasMore = false;
    let chatLoading = false;
    const chatMessageIds = new Set();

    function renderUserMode() {
      chatHasMore = false;
      chatLoading = false;
      chatMessageIds.clear();
      const adminButton = currentSessionRole === 'admin' ? '<button class="secondary" onclick="setAdminMode()">Режим админа</button>' : '';
      root.innerHTML = `<div class="miniapp-head"><div><div class="eyebrow">KobraS1Bot</div><h1>Режим пользователя</h1><p class="muted">Задайте вопрос боту.</p></div>${adminButton}</div>
        <section class="miniapp-grid"><article class="miniapp-card miniapp-card--wide chat-card">
          <div id="chat-history" aria-live="polite"></div>
          <div id="chat-status" class="chat-status muted" aria-live="polite"></div>
          <form onsubmit="sendChatMessage(event)" class="chat-form"><textarea id="chat-input" aria-label="Вопрос боту" placeholder="Например: как выставить первый слой?"></textarea><button id="chat-send" type="submit">Отправить</button></form>
        </article></section>`;
      loadChatHistory();
    }

    function appendChatMessage(message, prepend = false) {
      const history = document.getElementById('chat-history');
      if (!history || message.id != null && chatMessageIds.has(message.id)) return;
      if (message.id != null) chatMessageIds.add(message.id);
      const item = document.createElement('div');
      item.className = 'chat-message chat-message--' + (message.role === 'user' ? 'user' : 'bot');
      if (message.id != null) item.dataset.id = message.id;
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble';
      bubble.textContent = message.text || '';
      if (message.url && /^https?:\\/\\//i.test(message.url)) {
        const link = document.createElement('a');
        link.href = message.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'Открыть страницу вики';
        bubble.appendChild(document.createElement('br'));
        bubble.appendChild(link);
      }
      item.appendChild(bubble);
      if (prepend) history.insertBefore(item, history.firstChild); else history.appendChild(item);
    }

    function loadChatHistory(beforeId = null) {
      if (chatLoading) return;
      const history = document.getElementById('chat-history');
      if (!history) return;
      chatLoading = true;
      const oldHeight = history.scrollHeight;
      const oldTop = history.scrollTop;
      const query = new URLSearchParams({limit: '50'});
      if (beforeId != null) query.set('before_id', beforeId);
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/chat/history?' + query.toString(), {headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка загрузки истории'); return data; })
        .then((data) => {
          const prepend = beforeId != null;
          const messages = data.messages || [];
          (prepend ? [...messages].reverse() : messages).forEach((message) => appendChatMessage(message, prepend));
          chatHasMore = Boolean(data.has_more);
          const button = document.getElementById('chat-load-more');
          if (button) button.remove();
          if (chatHasMore) {
            const loadMore = document.createElement('button');
            loadMore.id = 'chat-load-more'; loadMore.type = 'button'; loadMore.className = 'secondary chat-load-more';
            loadMore.textContent = 'Загрузить предыдущие сообщения';
            loadMore.onclick = () => loadChatHistory(history.querySelector('.chat-message')?.dataset.id || (data.messages || [])[0]?.id);
            history.insertBefore(loadMore, history.firstChild);
          }
          if (prepend) history.scrollTop = history.scrollHeight - oldHeight + oldTop; else history.scrollTop = history.scrollHeight;
        })
        .catch((error) => { const status = document.getElementById('chat-status'); if (status) status.textContent = error.message; })
        .finally(() => { chatLoading = false; });
    }

    function sendChatMessage(event) {
      event.preventDefault();
      const input = document.getElementById('chat-input');
      const button = document.getElementById('chat-send');
      const status = document.getElementById('chat-status');
      const text = input && input.value.trim();
      if (!input || !button || !text || button.disabled) return;
      input.disabled = true; button.disabled = true; button.textContent = 'Ищу ответ…'; status.textContent = '';
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/chat/message', {method:'POST', headers:{Authorization:'Bearer ' + token, 'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams({text})})
        .then(async (response) => { const data = await response.json(); if (data.messages) data.messages.forEach((message) => appendChatMessage(message)); if (!response.ok) { const wait = data.retry_after != null ? ` Повторите через ${data.retry_after} с.` : ''; throw new Error((data.error || 'Ошибка отправки') + wait); } input.value = ''; })
        .catch((error) => { status.textContent = error.message; })
        .finally(() => { input.disabled = false; button.disabled = false; button.textContent = 'Отправить'; input.focus(); const history = document.getElementById('chat-history'); if (history) history.scrollTop = history.scrollHeight; });
    }
    function setUserMode() { renderUserMode(); }
    function setAdminMode() { loadDashboard(); }
    function loadDashboard() {
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/dashboard', {headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка загрузки'); renderDashboard(data); })
        .catch((error) => { root.innerHTML = '<div class="miniapp-error"><p class="error">' + escapeHtml(error.message) + '</p></div>'; });
    }
    function loadMissed() {
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/missed', {headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка загрузки'); renderMissed(data.items); })
        .catch((error) => { const box = document.getElementById('missed'); if (box) box.innerHTML = '<span class="error">' + escapeHtml(error.message) + '</span>'; });
    }
    function searchWiki(event) {
      event.preventDefault();
      const query = document.getElementById('wiki-query').value;
      const box = document.getElementById('search-results');
      const token = sessionStorage.getItem('kobra_app_session');
      fetch('/api/app/search?q=' + encodeURIComponent(query), {headers:{Authorization:'Bearer ' + token}})
        .then(async (response) => { const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Ошибка поиска'); box.innerHTML = data.results.length ? data.results.map((item) => '<p><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener" style="color:var(--blue)">' + escapeHtml(item.title) + '</a> · ' + item.score + '</p>').join('') : 'Ничего не найдено.'; })
        .catch((error) => { box.innerHTML = '<span class="error">' + escapeHtml(error.message) + '</span>'; });
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
      root.innerHTML = '<div class="miniapp-error"><p>Откройте приложение через Telegram.</p></div>';
    } else {
      fetch('/api/app/session', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: new URLSearchParams({init_data: tg.initData})
      }).then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Не удалось войти');
        sessionStorage.setItem('kobra_app_session', data.session);
        currentSessionRole = data.role;
        if (data.role === 'admin') loadDashboard(); else renderUserMode();
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
    """Проверяет Telegram initData и создаёт короткую сессию участника группы."""
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
    if _check_group_admin(application, user_id):
        role = "admin"
    elif _check_group_member(application, user_id):
        role = "user"
    else:
        return 403, {"error": "Доступ доступен только участникам группы."}

    token = secrets.token_urlsafe(32)
    ttl = min(max(300, int(getattr(state.settings, "panel_session_ttl_seconds", 1800))), 3600)
    with state.lock:
        sessions = _session_store(state)
        now = time.time()
        for old_token, session in list(sessions.items()):
            if float(session.get("exp", 0)) <= now:
                sessions.pop(old_token, None)
        sessions[token] = {"exp": now + ttl, "user": user, "role": role}
    return 200, {"session": token, "user": user, "role": role, "capabilities": {"admin": role == "admin"}}


def _check_group_admin(application: Any, user_id: int) -> bool:
    """Запускает Telegram-проверку в основном loop PTB, а не в HTTP-потоке."""
    return _run_group_access_check(application, user_id, is_group_admin)


def _check_group_member(application: Any, user_id: int) -> bool:
    """Проверяет членство в основном loop PTB, а не в HTTP-потоке."""
    return _run_group_access_check(application, user_id, is_group_member)


def _run_group_access_check(application: Any, user_id: int, check: Any) -> bool:
    """Выполняет coroutine проверки статуса через основной loop приложения."""
    main_loop = (getattr(application, "bot_data", None) or {}).get("main_loop")
    if main_loop is not None and main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(check(application, user_id), main_loop)
        try:
            return bool(future.result(timeout=15))
        except Exception:
            future.cancel()
            return False
    try:
        return bool(asyncio.run(check(application, user_id)))
    except Exception:
        return False


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


def _require_admin_session(state: Any, authorization: str) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
    session = _get_session(state, authorization)
    if session is None:
        return None, (401, {"error": "Сессия Mini App отсутствует или истекла."})
    if session.get("role") != "admin":
        return None, (403, {"error": "Для этого действия нужны права администратора группы."})
    return session, None


def dashboard_payload(state: Any, authorization: str) -> tuple[int, dict[str, Any]]:
    session, error = _require_admin_session(state, authorization)
    if error is not None:
        return error
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


def search_payload(state: Any, authorization: str, query: str) -> tuple[int, dict[str, Any]]:
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"error": "Сессия Mini App отсутствует или истекла."}
    query = query.strip()
    if not 2 <= len(query) <= 500:
        return 400, {"error": "Введите запрос длиной от 2 до 500 символов."}
    index = (state.application.bot_data if state.application else {}).get("wiki_index")
    if index is None:
        return 503, {"error": "Индекс вики ещё не готов."}
    try:
        matches = index.search(query, top_k=5)
    except Exception:
        return 500, {"error": "Поиск временно недоступен."}
    results = []
    for doc, score in matches:
        results.append({"title": str(getattr(doc, "title", "")), "url": str(getattr(doc, "url", "")), "score": int(score)})
    return 200, {"role": session["role"], "results": results}


def question_payload(state: Any, authorization: str, text: str) -> tuple[int, dict[str, Any]]:
    """Обработать вопрос в предпросмотре пользовательского режима."""
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"error": "Сессия Mini App отсутствует или истекла."}
    text = text.strip()
    if not 2 <= len(text) <= 2000:
        return 400, {"error": "Вопрос должен содержать от 2 до 2000 символов."}

    bot_data = state.application.bot_data if state.application else {}
    manual = find_manual_qa_answer(bot_data.get("manual_qa_entries") or [], text)
    if manual is not None:
        answer, title = manual
        return 200, {"answered": True, "source": "manual", "answer": answer, "title": title}

    index = bot_data.get("wiki_index")
    matches = index.search(text, top_k=1) if index is not None else []
    if matches:
        doc, score = matches[0]
        score = int(score)
        url = str(getattr(doc, "url", ""))
        title = str(getattr(doc, "title", ""))
        if score >= int(getattr(state.settings, "min_score", 72)):
            return 200, {
                "answered": True,
                "source": "wiki",
                "answer": f"Нашёл подходящую страницу: «{title}»." if title else "Нашёл подходящую страницу вики.",
                "title": title,
                "url": url,
                "score": score,
            }
        best_url = url
    else:
        score = None
        best_url = None

    add_missed_question(
        text=text,
        score=score,
        best_url=best_url,
        chat_id=getattr(state.settings, "panel_admin_chat_id", None),
    )
    return 200, {
        "answered": False,
        "source": "missing",
        "answer": "Пока я не могу ответить на этот вопрос. Попробуйте задать его в чате группы или повторить позже.",
    }


def _chat_message_payload(message: Any) -> dict[str, Any]:
    return {
        "id": message.id,
        "user_id": message.user_id,
        "role": message.role,
        "text": message.text,
        "source": message.source,
        "created_at": message.created_at,
        "reply_to_id": message.reply_to_id,
    }


def _chat_store(state: Any) -> Any:
    return getattr(state, "chat_store", None)


def chat_history_payload(
    state: Any, authorization: str, limit: int, before_id: int | None
) -> tuple[int, dict[str, Any]]:
    """Возвращает сохранённую историю только текущего пользователя."""
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"error": "Сессия Mini App отсутствует или истекла."}
    store = _chat_store(state)
    if store is None:
        return 503, {"error": "История чата временно недоступна."}

    user_id = int(session["user"]["id"])
    limit = max(1, min(50, limit))
    messages = store.list_messages(user_id, limit=limit + 1, before_id=before_id)
    has_more = len(messages) > limit
    if has_more:
        messages = messages[1:]
    return 200, {
        "role": session["role"],
        "user": session["user"],
        "messages": [_chat_message_payload(message) for message in messages],
        "has_more": has_more,
    }


def _chat_pair_payload(session: dict[str, Any], user_message: Any, bot_message: Any) -> dict[str, Any]:
    return {
        "role": session["role"],
        "user": session["user"],
        "messages": [_chat_message_payload(user_message), _chat_message_payload(bot_message)],
    }


def chat_message_payload(state: Any, authorization: str, text: str) -> tuple[int, dict[str, Any]]:
    """Сохраняет вопрос участника и ответ бота из manual_qa или вики."""
    session = _get_session(state, authorization)
    if session is None:
        return 401, {"error": "Сессия Mini App отсутствует или истекла."}
    text = text.strip()
    if not 2 <= len(text) <= 2000:
        return 400, {"error": "Вопрос должен содержать от 2 до 2000 символов."}
    store = _chat_store(state)
    if store is None:
        return 503, {"error": "История чата временно недоступна."}

    user_id = int(session["user"]["id"])
    duplicate = store.find_recent_duplicate(user_id, text)
    if duplicate is not None:
        return 200, _chat_pair_payload(session, *duplicate)

    allowed, retry_after = store.allow_request(user_id)
    if not allowed:
        return 429, {"error": "Слишком много сообщений. Повторите позже.", "retry_after": retry_after}

    user_message = store.add_message(user_id, "user", text, "miniapp")
    bot_data = state.application.bot_data if state.application else {}
    manual = find_manual_qa_answer(bot_data.get("manual_qa_entries") or [], text)
    if manual is not None:
        answer, _ = manual
        bot_message = store.add_message(user_id, "bot", answer, "manual", reply_to_id=user_message.id)
        store.prune_user_history(user_id, keep=500)
        return 200, _chat_pair_payload(session, user_message, bot_message)

    try:
        index = bot_data.get("wiki_index")
        matches = index.search(text, top_k=1) if index is not None else []
    except Exception:
        bot_message = store.add_message(
            user_id,
            "bot",
            "Поиск по вики временно недоступен. Попробуйте повторить вопрос позже.",
            "error",
            reply_to_id=user_message.id,
        )
        store.prune_user_history(user_id, keep=500)
        return 503, _chat_pair_payload(session, user_message, bot_message)

    if matches:
        doc, score = matches[0]
        title = str(getattr(doc, "title", ""))
        if int(score) >= int(getattr(state.settings, "min_score", 72)):
            answer = f"Нашёл подходящую страницу: «{title}»." if title else "Нашёл подходящую страницу вики."
            bot_message = store.add_message(user_id, "bot", answer, "wiki", reply_to_id=user_message.id)
            store.prune_user_history(user_id, keep=500)
            return 200, _chat_pair_payload(session, user_message, bot_message)
        best_url = str(getattr(doc, "url", "")) or None
        best_score = int(score)
    else:
        best_url = None
        best_score = None

    add_missed_question(
        text=text,
        score=best_score,
        best_url=best_url,
        chat_id=getattr(state.settings, "panel_admin_chat_id", None),
    )
    bot_message = store.add_message(
        user_id,
        "bot",
        "Пока я не могу ответить на этот вопрос. Попробуйте задать его в чате группы или повторить позже.",
        "missing",
        reply_to_id=user_message.id,
    )
    store.prune_user_history(user_id, keep=500)
    return 200, _chat_pair_payload(session, user_message, bot_message)


def missed_payload(state: Any, authorization: str) -> tuple[int, dict[str, Any]]:
    session, error = _require_admin_session(state, authorization)
    if error is not None:
        return error
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
    session, error = _require_admin_session(state, authorization)
    if error is not None:
        status, payload = error
        return status, {"ok": False, **payload}
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
    session, error = _require_admin_session(state, authorization)
    if error is not None:
        status, payload = error
        return status, {"ok": False, **payload}
    entry = _find_missed(item_id)
    if entry is None:
        return 404, {"ok": False, "error": "Вопрос уже обработан или не найден."}
    ok, message = delete_missed_question_by_text(text=str(entry.get("text", "")))
    return (200 if ok else 500), {"ok": ok, "message": message} if ok else {"ok": False, "error": message}
