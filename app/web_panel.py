"""Встроенная веб-панель администратора (без внешних зависимостей).

Поднимается в фоновом потоке внутри того же процесса, что и бот, поэтому
стартует вместе с ним. Вход — по логину/паролю (см. PANEL_* в .env).

Возможности:
- Дашборд: статус бота, размер индекса вики, счётчики записей.
- Ручные ответы (manual_qa.json): просмотр / добавление / редактирование / удаление.
- Фиксы ссылок (fixes.json): просмотр / добавление / удаление.
- Логи решений: хвост logs/bot.log с фильтром.

Правки ручных ответов и фиксов сразу применяются к работающему боту
(через ``Application.bot_data``), перезапуск не нужен.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import threading
import time
import urllib.request
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from app.bot.git_autopull import (
    git_ping_compare_with_remote,
    git_sync_from_remote,
    project_repo_root,
    schedule_restart_after_pull,
)
from app.bot.panel_login import consume_authorized, create_login_code, get_code_status
from app.bot.bad_answers import (
    delete_bad_answer,
    flag_bad_answer,
    load_bad_answers,
    try_git_push_bad_answers,
)
from app.bot.missed_questions import (
    clear_missed_questions,
    delete_missed_question,
    load_missed_questions,
)
from app.bot.reply_logging import save_recent_replies
from app.bot.manual_qa import (
    add_manual_qa_entry,
    delete_manual_qa_by_index,
    load_manual_qa_store,
    save_manual_qa_store,
    try_git_push_manual_qa,
)
from app.bot.stores import _load_fix_store, _norm_text, _save_fix_store
from app.bot.bot_stats import get_top_wiki_pages, get_top_questions, get_hourly_activity

log = logging.getLogger(__name__)

_COOKIE_NAME = "panel_session"

# Поля, которые присылает Telegram Login Widget (порядок неважен — сортируем при проверке).
_TG_FIELDS = ("id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash")


def _verify_telegram_auth(data: dict[str, str], bot_token: str, *, max_age: int = 86400) -> tuple[bool, str]:
    """Проверка подписи данных от Telegram Login Widget (HMAC-SHA256 по sha256(token))."""
    recv_hash = data.get("hash", "")
    if not recv_hash:
        return False, "нет подписи"
    pairs = sorted(f"{k}={v}" for k, v in data.items() if k != "hash" and v != "")
    data_check_string = "\n".join(pairs)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    calc = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return False, "подпись не совпала"
    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if auth_date <= 0 or (time.time() - auth_date) > max_age:
        return False, "данные входа устарели, попробуйте снова"
    return True, ""


def _telegram_api(token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}?" + urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "KobraPanel"})
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 (доверенный домен api.telegram.org)
        return json.load(r)


def _sessions_file() -> Path:
    from app.bot.git_autopull import project_repo_root
    return project_repo_root() / ".cache" / "panel_sessions.json"


class _PanelState:
    """Общее состояние панели: ссылка на бота, настройки, сессии."""

    def __init__(self, application: Any, settings: Any) -> None:
        self.application = application
        self.settings = settings
        self.start_time = time.time()
        # token -> {"exp": float, "csrf": str, "user": str}
        self.sessions: dict[str, dict[str, Any]] = {}
        # ip -> [timestamps] неудачных попыток входа
        self.login_fails: dict[str, list[float]] = {}
        # кэш админов группы: {"chat": int, "ids": set[int], "exp": float}
        self.admin_cache: dict[str, Any] = {}
        self.lock = threading.Lock()
        self._load_sessions()

    def _load_sessions(self) -> None:
        """Загружает живые (не истёкшие) сессии с прошлого запуска."""
        try:
            p = _sessions_file()
            if not p.exists():
                return
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            now = time.time()
            self.sessions = {
                t: s for t, s in raw.items()
                if isinstance(s, dict) and isinstance(s.get("exp"), (int, float)) and s["exp"] > now
            }
        except Exception:
            pass

    def _save_sessions_locked(self) -> None:
        """Сохраняет текущие сессии на диск (вызывается под self.lock)."""
        try:
            p = _sessions_file()
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(json.dumps(self.sessions, ensure_ascii=False).encode("utf-8"))
            tmp.replace(p)
        except Exception as exc:
            logging.warning("panel: не удалось сохранить сессии: %s", exc)

    # --- сессии ---
    def new_session(self, user: str = "") -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(16)
        ttl = max(60, int(getattr(self.settings, "panel_session_ttl_seconds", 86400)))
        with self.lock:
            self.sessions[token] = {"exp": time.time() + ttl, "csrf": csrf, "user": user}
            self._gc_locked()
            self._save_sessions_locked()
        return token, csrf

    def admin_ids(self, token: str, chat_id: int, *, ttl: int = 60) -> tuple[set[int] | None, str | None]:
        """Множество user_id админов группы (с кэшем). Возвращает (ids, ошибка)."""
        with self.lock:
            c = self.admin_cache
            if c and c.get("chat") == chat_id and c.get("exp", 0) > time.time():
                return set(c["ids"]), None
        try:
            resp = _telegram_api(token, "getChatAdministrators", {"chat_id": chat_id})
        except Exception as e:  # noqa: BLE001
            return None, f"не удалось получить список админов: {e}"
        if not resp.get("ok"):
            return None, f"Telegram: {resp.get('description', 'ошибка')}"
        ids: set[int] = set()
        for m in resp.get("result", []):
            u = m.get("user") or {}
            uid = u.get("id")
            if uid is not None and not u.get("is_bot"):
                ids.add(int(uid))
        with self.lock:
            self.admin_cache = {"chat": chat_id, "ids": set(ids), "exp": time.time() + ttl}
        return ids, None

    def get_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.lock:
            s = self.sessions.get(token)
            if not s:
                return None
            if s["exp"] < time.time():
                self.sessions.pop(token, None)
                return None
            return s

    def drop_session(self, token: str | None) -> None:
        if not token:
            return
        with self.lock:
            self.sessions.pop(token, None)
            self._save_sessions_locked()

    def _gc_locked(self) -> None:
        now = time.time()
        dead = [t for t, s in self.sessions.items() if s["exp"] < now]
        for t in dead:
            self.sessions.pop(t, None)

    # --- троттлинг входа ---
    def login_blocked(self, ip: str) -> bool:
        now = time.time()
        with self.lock:
            fails = [t for t in self.login_fails.get(ip, []) if now - t < 300]
            self.login_fails[ip] = fails
            return len(fails) >= 8

    def record_login_fail(self, ip: str) -> None:
        now = time.time()
        with self.lock:
            self.login_fails.setdefault(ip, []).append(now)

    def clear_login_fails(self, ip: str) -> None:
        with self.lock:
            self.login_fails.pop(ip, None)


# ------------------------- HTML -------------------------

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0;
  background: #0f1115; color: #e6e6e6; }
a { color: #5aa9ff; text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: #161a22; padding: 12px 20px; border-bottom: 1px solid #262b36;
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
header .brand { font-weight: 700; color: #fff; }
header nav a { margin-right: 14px; }
header .spacer { flex: 1; }
main { padding: 20px; max-width: 1100px; margin: 0 auto; }
h1, h2 { color: #fff; }
.card { background: #161a22; border: 1px solid #262b36; border-radius: 10px;
  padding: 16px 18px; margin-bottom: 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.stat { background: #1b2030; border-radius: 8px; padding: 14px; }
.stat .n { font-size: 26px; font-weight: 700; color: #fff; }
.stat .l { color: #9aa4b2; font-size: 13px; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #262b36;
  vertical-align: top; font-size: 14px; }
th { color: #9aa4b2; font-weight: 600; }
input[type=text], input[type=password], textarea, input[type=number] {
  width: 100%; background: #0f1115; color: #e6e6e6; border: 1px solid #2c3340;
  border-radius: 6px; padding: 9px 10px; font-size: 14px; font-family: inherit; }
textarea { min-height: 90px; resize: vertical; }
label { display: block; margin: 10px 0 4px; color: #9aa4b2; font-size: 13px; }
button, .btn { background: #2563eb; color: #fff; border: 0; border-radius: 6px;
  padding: 9px 16px; font-size: 14px; cursor: pointer; }
button:hover { background: #1d4ed8; }
.btn-danger { background: #b91c1c; }
.btn-danger:hover { background: #991b1b; }
.btn-sm { padding: 5px 10px; font-size: 13px; }
.muted { color: #9aa4b2; }
.flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; }
.flash.ok { background: #14331f; border: 1px solid #1f6b3a; color: #9be7b4; }
.flash.err { background: #3a1414; border: 1px solid #6b1f1f; color: #f0a0a0; }
pre.logs { background: #0b0d12; border: 1px solid #262b36; border-radius: 8px;
  padding: 12px; overflow: auto; max-height: 70vh; font-size: 12.5px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word; }
.kv code { background: #0f1115; padding: 2px 6px; border-radius: 4px; }
.inline { display: inline; }
.right { text-align: right; }
form.inline-form { display: inline; }
.login-wrap { max-width: 360px; margin: 80px auto; }
.badge { display: inline-block; font-size: 11px; padding: 2px 6px; border-radius: 4px;
  background: #1b2030; color: #9aa4b2; border: 1px solid #2c3340; white-space: nowrap; }
.badge-faq { background: #14331f; color: #9be7b4; border-color: #1f6b3a; }
.badge-wiki { background: #0f2040; color: #7ab8ff; border-color: #1a3a6b; }
.badge-err { background: #3a1414; color: #f0a0a0; border-color: #6b1f1f; }
td.q-cell { max-width: 280px; word-break: break-word; }
td.a-cell { max-width: 320px; word-break: break-word; }
"""


def _layout(state: _PanelState, body: str, *, title: str = "Панель бота", flash: str = "", csrf: str = "") -> bytes:
    bot = state.application.bot_data.get("bot_username") if state.application else None
    nav = (
        '<nav>'
        '<a href="/">Дашборд</a>'
        '<a href="/qa">Ручные ответы</a>'
        '<a href="/fixes">Фиксы ссылок</a>'
        '<a href="/logs">Логи</a>'
        '<a href="/config">Настройки</a>'
        '</nav>'
    )
    upd = ""
    if csrf:
        upd = (
            '<form class="inline-form" method="post" action="/update/check">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            '<button class="btn btn-sm" style="background:#374151" type="submit" '
            'title="git fetch и сравнение с GitHub">Проверить обновления</button></form> '
            '<form class="inline-form" method="post" action="/update/run" '
            "onsubmit=\"return confirm('Обновить бота из git и перезапустить?')\">"
            f'<input type="hidden" name="csrf" value="{csrf}">'
            '<button class="btn btn-sm" style="background:#b45309" type="submit" '
            'title="git pull и перезапуск">Обновить</button></form>'
        )
    head = (
        '<header>'
        f'<span class="brand">🤖 {html.escape("@" + bot) if bot else "Бот"}</span>'
        f'{nav}'
        '<span class="spacer"></span>'
        f'{upd}'
        '<a href="/logout" style="margin-left:14px">Выйти</a>'
        '</header>'
    )
    page = (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f"{head}<main>{flash}{body}</main></body></html>"
    )
    return page.encode("utf-8")


def _login_page(state: _PanelState, *, error: str = "") -> bytes:
    err = f'<div class="flash err">{html.escape(error)}</div>' if error else ""
    bd = state.application.bot_data if state.application else {}
    bot_user = bd.get("bot_username")
    st = state.settings
    tg_enabled = bool(
        getattr(st, "panel_tg_login", False)
        and bot_user
        and getattr(st, "panel_admin_chat_id", None)
        and getattr(st, "telegram_bot_token", "")
    )
    pwd_enabled = bool(getattr(st, "panel_password", ""))

    tg_block = ""
    if tg_enabled:
        tg_block = (
            '<p class="muted">Доступ только у администраторов группы. Вход через бота — домен не нужен:</p>'
            '<form method="post" action="/bot-login/new" style="margin:8px 0 4px">'
            '<button type="submit">🔐 Войти через Telegram-бота</button>'
            "</form>"
        )

    pwd_block = ""
    if pwd_enabled:
        sep = '<div class="muted" style="text-align:center;margin:14px 0">— или —</div>' if tg_block else ""
        pwd_block = (
            f"{sep}"
            '<form method="post" action="/login">'
            '<label>Логин</label><input type="text" name="username">'
            '<label>Пароль</label><input type="password" name="password">'
            '<div style="margin-top:16px"><button type="submit">Войти по паролю</button></div>'
            "</form>"
        )

    if not tg_block and not pwd_block:
        pwd_block = '<p class="muted">Способы входа не настроены (PANEL_TG_LOGIN / PANEL_PASSWORD).</p>'

    body = (
        '<div class="login-wrap"><div class="card">'
        "<h2>Вход в панель</h2>"
        f"{err}{tg_block}{pwd_block}"
        "</div></div>"
    )
    page = (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>Вход</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>"
    )
    return page.encode("utf-8")


def _bot_login_wait_page(bot_user: str, code: str) -> bytes:
    deep_link = f"https://t.me/{bot_user}?start={code}"
    body = (
        '<div class="login-wrap"><div class="card">'
        "<h2>Вход через бота</h2>"
        "<ol class=muted style='padding-left:18px;line-height:1.7'>"
        "<li>Нажмите кнопку — откроется бот.</li>"
        "<li>В боте нажмите <b>Start</b> (Запустить).</li>"
        "<li>Вернитесь сюда — страница откроется сама.</li>"
        "</ol>"
        f'<a class="btn" href="{html.escape(deep_link)}" target="_blank" rel="noopener" '
        'style="display:inline-block;margin:6px 0 12px">Открыть бота</a>'
        '<p id="st" class="muted">Ожидание подтверждения…</p>'
        '<p><a href="/login">← назад</a></p>'
        "</div></div>"
        "<script>"
        f"var code={json.dumps(code)};"
        "function poll(){fetch('/bot-login/status?code='+encodeURIComponent(code))"
        ".then(function(r){return r.text()}).then(function(s){"
        "var el=document.getElementById('st');"
        "if(s==='authorized'){el.textContent='Готово, входим…';"
        "location='/bot-login/finish?code='+encodeURIComponent(code);}"
        "else if(s==='denied'){el.textContent='⛔ Отказано: вы не администратор группы.';}"
        "else if(s==='expired'){el.textContent='Срок действия истёк. Обновите страницу и начните заново.';}"
        "else{setTimeout(poll,2000);}"
        "}).catch(function(){setTimeout(poll,3000);});}"
        "setTimeout(poll,2000);"
        "</script>"
    )
    page = (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>Вход через бота</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>"
    )
    return page.encode("utf-8")


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}д")
    if h or d:
        parts.append(f"{h}ч")
    parts.append(f"{m}м")
    return " ".join(parts)


def _source_badge(source: str) -> str:
    labels = {"manual_qa": ("FAQ", "badge-faq"), "wiki": ("Вики", "badge-wiki"), "error_code": ("Ошибка", "badge-err")}
    label, cls = labels.get(source, (html.escape(source) or "?", ""))
    return f'<span class="badge {cls}">{label}</span>'


def _recent_replies_section(state: _PanelState, csrf: str) -> str:
    """HTML-блок ленты последних ответов бота с кнопкой «Отметить ошибочным»."""
    replies: list[dict] = (state.application.bot_data.get("recent_replies") or []) if state.application else []
    if not replies:
        return (
            '<div class="card">'
            '<h2>Последние ответы бота</h2>'
            '<p class="muted">Ответов ещё нет — появятся после первого срабатывания бота в чате.</p>'
            '</div>'
        )
    rows = []
    for i, r in enumerate(replies[:30]):
        ts = time.strftime("%d.%m %H:%M", time.localtime(float(r.get("ts", 0) or 0)))
        q = html.escape(str(r.get("question", ""))[:300])
        ans = str(r.get("answer", ""))
        url = str(r.get("url", ""))
        source = str(r.get("source", ""))
        if url:
            ans_cell = f'<a href="{html.escape(url)}" target=_blank rel=noopener>{html.escape(url[:90])}</a>'
        else:
            ans_cell = f'<span class=muted>{html.escape(ans[:250])}</span>'
        rows.append(
            "<tr>"
            f'<td class=muted style="white-space:nowrap;font-size:12px">{html.escape(ts)}</td>'
            f"<td>{_source_badge(source)}</td>"
            f'<td class="q-cell">{q}</td>'
            f'<td class="a-cell">{ans_cell}</td>'
            "<td class=right>"
            '<form class="inline-form" method="post" action="/replies/flag">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="i" value="{i}">'
            '<button class="btn btn-sm btn-danger" type="submit" title="Отметить как ошибочный">⚑</button>'
            "</form>"
            "</td></tr>"
        )
    table = (
        "<table>"
        "<colgroup>"
        '<col style="width:8%"><col style="width:7%"><col style="width:38%">'
        '<col style="width:42%"><col style="width:5%">'
        "</colgroup>"
        "<tr><th>Время</th><th>Тип</th><th>Вопрос</th><th>Ответ / URL</th><th></th></tr>"
        + "".join(rows)
        + "</table>"
    )
    return f'<div class="card"><h2>Последние ответы бота</h2>{table}</div>'


def _bad_answers_section(state: _PanelState, csrf: str) -> str:
    """HTML-блок отмеченных ошибочных ответов с кнопкой удаления."""
    entries = load_bad_answers()
    if not entries:
        return ""
    rows = []
    for i, e in enumerate(entries[:50]):
        ts = time.strftime("%d.%m %H:%M", time.localtime(float(e.get("ts", 0) or 0)))
        q = html.escape(str(e.get("question", ""))[:300])
        ans = str(e.get("answer", ""))
        url = str(e.get("url", ""))
        source = str(e.get("source", ""))
        note = html.escape(str(e.get("note", ""))[:200])
        if url:
            ans_cell = f'<a href="{html.escape(url)}" target=_blank rel=noopener>{html.escape(url[:90])}</a>'
        else:
            ans_cell = f'<span class=muted>{html.escape(ans[:250])}</span>'
        note_block = f'<br><span class=muted style="font-size:12px">{note}</span>' if note else ""
        rows.append(
            "<tr>"
            f'<td class=muted style="white-space:nowrap;font-size:12px">{html.escape(ts)}</td>'
            f"<td>{_source_badge(source)}</td>"
            f'<td class="q-cell">{q}</td>'
            f'<td class="a-cell">{ans_cell}{note_block}</td>'
            "<td class=right>"
            '<form class="inline-form" method="post" action="/bad-answers/delete"'
            " onsubmit=\"return confirm('Удалить запись?')\">"
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="i" value="{i}">'
            '<button class="btn btn-sm" style="background:#374151" type="submit" title="Удалить после обработки">✓ Обработано</button>'
            "</form>"
            "</td></tr>"
        )
    table = (
        "<table>"
        "<colgroup>"
        '<col style="width:8%"><col style="width:7%"><col style="width:37%">'
        '<col style="width:40%"><col style="width:8%">'
        "</colgroup>"
        "<tr><th>Время</th><th>Тип</th><th>Вопрос</th><th>Ответ / URL</th><th></th></tr>"
        + "".join(rows)
        + "</table>"
    )
    return (
        '<div class="card" style="border-color:#6b1f1f">'
        f'<h2 style="color:#f0a0a0">⚑ Ошибочные ответы ({len(entries)})</h2>'
        f"{table}"
        "</div>"
    )


def _missed_questions_section(csrf: str) -> str:
    """HTML-блок вопросов без ответа с кнопкой удаления и очистки всего списка."""
    entries = load_missed_questions()
    if not entries:
        return ""
    rows = []
    for i, e in enumerate(entries[:100]):
        ts = time.strftime("%d.%m %H:%M", time.localtime(float(e.get("ts", 0) or 0)))
        q = html.escape(str(e.get("text", ""))[:300])
        score = e.get("score")
        score_str = f"{score:.0f}" if score is not None else "—"
        url = str(e.get("best_url", "") or "")
        count = int(e.get("count", 1))
        url_cell = (
            f'<a href="{html.escape(url)}" target=_blank rel=noopener style="font-size:12px">{html.escape(url[:70])}</a>'
            if url else '<span class=muted>—</span>'
        )
        count_badge = (
            f' <span style="background:#374151;border-radius:4px;padding:1px 5px;font-size:11px">{count}×</span>'
            if count > 1 else ""
        )
        rows.append(
            "<tr>"
            f'<td class=muted style="white-space:nowrap;font-size:12px">{html.escape(ts)}</td>'
            f'<td class=muted style="text-align:center">{html.escape(score_str)}</td>'
            f'<td class="q-cell">{q}{count_badge}</td>'
            f'<td class="a-cell">{url_cell}</td>'
            "<td class=right>"
            '<form class="inline-form" method="post" action="/missed-questions/delete">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="i" value="{i}">'
            '<button class="btn btn-sm" style="background:#374151" type="submit" title="Удалить запись">✓</button>'
            "</form>"
            "</td></tr>"
        )
    table = (
        "<table>"
        "<colgroup>"
        '<col style="width:9%"><col style="width:5%"><col style="width:46%">'
        '<col style="width:33%"><col style="width:7%">'
        "</colgroup>"
        "<tr><th>Время</th><th>Score</th><th>Вопрос</th><th>Лучший URL</th><th></th></tr>"
        + "".join(rows)
        + "</table>"
    )
    clear_btn = (
        '<form class="inline-form" method="post" action="/missed-questions/clear"'
        " onsubmit=\"return confirm('Очистить весь список?')\" style='margin-top:8px'>"
        f'<input type="hidden" name="csrf" value="{csrf}">'
        '<button class="btn btn-sm" style="background:#374151" type="submit">🗑 Очистить всё</button>'
        "</form>"
    )
    return (
        '<div class="card" style="border-color:#1f4a6b">'
        f'<h2 style="color:#a0c8f0">❓ Вопросы без ответа ({len(entries)})</h2>'
        f"{table}"
        f"{clear_btn}"
        "</div>"
    )


def _dashboard(state: _PanelState, csrf: str = "", flash: str = "") -> bytes:
    bd = state.application.bot_data if state.application else {}
    wix = bd.get("wiki_index")
    idxr = bd.get("wiki_indexer")
    qa = bd.get("manual_qa_entries") or []
    fixes = bd.get("fix_store") or {}
    codes = bd.get("error_codes_catalog") or {}
    doc_count = getattr(wix, "doc_count", 0) if wix is not None else 0
    try:
        index_done = idxr.is_done() if idxr is not None else False
    except Exception:
        index_done = False

    def stat(n: Any, label: str) -> str:
        return f'<div class="stat"><div class="n">{html.escape(str(n))}</div><div class="l">{html.escape(label)}</div></div>'

    bot_stats = bd.get("bot_stats") or {}
    total_answers = bot_stats.get("total_answers", 0)
    top_wiki_pages = get_top_wiki_pages(bd)
    top_questions = get_top_questions(bd)
    hourly_activity = get_hourly_activity(bd)

    stats = (
        stat(doc_count, "страниц вики в индексе")
        + stat("готов" if index_done else "идёт…", "индексация")
        + stat(len(qa), "ручных ответов")
        + stat(len(fixes), "фиксов ссылок")
        + stat(len(codes), "кодов ошибок")
        + stat(total_answers, "всего ответов бота")
        + stat(_fmt_uptime(time.time() - state.start_time), "аптайм панели")
    )
    st = state.settings
    _CFG_DESCRIPTIONS: list[tuple[str, Any, str]] = [
        ("MIN_SCORE",          getattr(st, "min_score", ""),          "Минимальный порог совпадения (0–100). Чем выше — тем реже бот отвечает, но точнее. Если бот молчит на очевидные вопросы — снизьте; если отвечает невпопад — повысьте."),
        ("CLARIFY_MIN_SCORE",  getattr(st, "clarify_min_score", ""),  "Порог для уточняющего вопроса о модели принтера. Если score найденной страницы выше этого значения, но ниже MIN_SCORE — бот спросит «какая у вас модель?» вместо молчания."),
        ("QUESTIONS_ONLY",     getattr(st, "questions_only", ""),     "Отвечать только на сообщения, похожие на вопрос (есть вопросительные слова, знак «?» и т.п.). При True бот игнорирует утверждения и комментарии."),
        ("REQUIRE_TRIGGER",    getattr(st, "require_trigger", ""),    "Отвечать только при явном обращении к боту: @упоминание или reply на сообщение бота. При False бот реагирует на все вопросы в разрешённых чатах автоматически."),
        ("LOG_DECISIONS",      getattr(st, "log_decisions", ""),      "Записывать в bot.log почему бот ответил или промолчал (cooldown, low_score, not_a_question и т.д.). Полезно при отладке, но увеличивает размер лога."),
        ("MANUAL_QA_GIT_PUSH", getattr(st, "manual_qa_git_push", ""), "Автоматически коммитить и пушить data/manual_qa.json в GitHub после каждого добавления/удаления ручного ответа через панель или команды бота."),
        ("PID",                os.getpid(),                           "ID процесса бота в системе. Используется для диагностики и управления процессом (kill, systemctl и т.д.)."),
    ]
    cfg_rows = "".join(
        f"<tr>"
        f"<td style='min-width:180px'><span style='font-size:13px;color:#e6e6e6'>{html.escape(k)}</span>"
        f"<br><span class=muted style='font-size:12px'>{html.escape(desc)}</span></td>"
        f"<td style='white-space:nowrap'><code>{html.escape(str(v))}</code></td>"
        f"</tr>"
        for k, v, desc in _CFG_DESCRIPTIONS
    )
    recent_section = _recent_replies_section(state, csrf) if csrf else ""
    bad_section = _bad_answers_section(state, csrf) if csrf else ""
    missed_section = _missed_questions_section(csrf) if csrf else ""
    bot_stats_section = _bot_stats_section(top_wiki_pages, top_questions, hourly_activity)
    body = (
        "<h1>Дашборд</h1>"
        f'<div class="card"><div class="grid">{stats}</div></div>'
        f"{bot_stats_section}"
        f"{bad_section}"
        f"{missed_section}"
        f"{recent_section}"
        '<div class="card kv"><h2>Конфигурация (только просмотр)</h2>'
        f"<table>{cfg_rows}</table>"
        '<p class="muted">Параметры задаются через переменные окружения / .env и применяются при запуске.</p>'
        "</div>"
    )
    return _layout(state, body, title="Дашборд", flash=flash, csrf=csrf)


def _bot_stats_section(
    top_wiki_pages: list[tuple[str, int]],
    top_questions: list[tuple[str, int]],
    hourly_activity: list[int],
) -> str:
    """HTML-карточка: топ вики-страниц, топ вопросов, активность по часам."""
    # Топ вики-страниц
    if top_wiki_pages:
        wiki_rows = "".join(
            f"<tr>"
            f'<td class=q-cell><a href="{html.escape(url)}" target=_blank rel=noopener>'
            f"{html.escape(url.rstrip('/').rsplit('/', 1)[-1][:60] or url[:60])}"
            f"</a></td>"
            f"<td class=right>{count}</td>"
            f"</tr>"
            for url, count in top_wiki_pages
        )
    else:
        wiki_rows = '<tr><td colspan=2 class=muted>Нет данных — бот ещё не отвечал</td></tr>'

    # Топ вопросов
    if top_questions:
        q_rows = "".join(
            f"<tr><td class=q-cell>{html.escape(q[:150])}</td><td class=right>{count}</td></tr>"
            for q, count in top_questions
        )
    else:
        q_rows = '<tr><td colspan=2 class=muted>Нет данных — бот ещё не отвечал</td></tr>'

    # Гистограмма активности по часам
    max_val = max(hourly_activity) if hourly_activity else 0
    scale = max_val or 1
    bar_rows = "".join(
        "<div style='font-size:11px;margin:2px 0;white-space:nowrap'>"
        f"<span style='display:inline-block;width:32px;color:#9aa4b2'>{h:02d}:00</span>"
        f"<span style='color:#5aa9ff'>{'█' * int((hourly_activity[h] / scale) * 18)}"
        f"{'░' * (18 - int((hourly_activity[h] / scale) * 18))}</span>"
        f" <span class=muted>{hourly_activity[h]}</span>"
        "</div>"
        for h in range(24)
    )

    return (
        '<div class="card">'
        "<h2>Статистика ответов</h2>"
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px">'
        "<div>"
        '<h3 style="margin-top:0;font-size:14px;color:#9aa4b2">Топ страниц вики</h3>'
        "<table>"
        "<tr><th>Страница</th><th class=right>Ответов</th></tr>"
        f"{wiki_rows}"
        "</table>"
        "</div>"
        "<div>"
        '<h3 style="margin-top:0;font-size:14px;color:#9aa4b2">Топ вопросов</h3>'
        "<table>"
        "<tr><th>Вопрос</th><th class=right>Раз</th></tr>"
        f"{q_rows}"
        "</table>"
        "</div>"
        "<div>"
        '<h3 style="margin-top:0;font-size:14px;color:#9aa4b2">Активность по часам</h3>'
        f"{bar_rows}"
        "</div>"
        "</div>"
        "</div>"
    )


def _qa_list(state: _PanelState, csrf: str, flash: str = "") -> bytes:
    entries = load_manual_qa_store()
    rows = []
    for i, e in enumerate(entries):
        keys = e.get("keys") or []
        title = e.get("title") or (keys[0] if keys else "—")
        answer = e.get("answer") or ""
        keys_html = "<br>".join(html.escape(str(k)) for k in keys)
        rows.append(
            "<tr>"
            f"<td class=muted>{i + 1}</td>"
            f"<td><b>{html.escape(str(title))}</b><br><span class=muted>{keys_html}</span></td>"
            f"<td>{html.escape(str(answer))}</td>"
            "<td class=right>"
            f'<a class="btn btn-sm" href="/qa/edit?i={i}">Изм.</a> '
            f'<form class="inline-form" method="post" action="/qa/delete" '
            f'onsubmit="return confirm(\'Удалить запись?\')">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="i" value="{i}">'
            f'<button class="btn btn-sm btn-danger" type="submit">Удал.</button></form>'
            "</td></tr>"
        )
    table = (
        "<table>"
        "<colgroup>"
        '<col style="width:3%">'
        '<col style="width:28%">'
        '<col style="width:57%">'
        '<col style="width:12%">'
        "</colgroup>"
        "<tr><th>#</th><th>Заголовок / ключи</th><th>Ответ</th><th></th></tr>"
        + ("".join(rows) or '<tr><td colspan=4 class=muted>Пока пусто</td></tr>')
        + "</table>"
    )
    add_form = (
        '<div class="card"><h2>Добавить ответ</h2>'
        '<form method="post" action="/qa/add">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        "<label>Заголовок</label><input type=text name=title>"
        "<label>Ключи (по одному на строку — фразы-триггеры, как пишут пользователи)</label>"
        "<textarea name=keys></textarea>"
        "<label>Ответ</label><textarea name=answer></textarea>"
        '<div style="margin-top:12px"><button type=submit>Добавить</button></div>'
        "</form></div>"
    )
    body = f"<h1>Ручные ответы</h1>{add_form}<div class=card>{table}</div>"
    return _layout(state, body, title="Ручные ответы", flash=flash, csrf=csrf)


def _qa_edit_page(state: _PanelState, idx: int, csrf: str, flash: str = "") -> bytes:
    entries = load_manual_qa_store()
    if idx < 0 or idx >= len(entries):
        return _layout(state, "<h1>Запись не найдена</h1>", flash=flash, csrf=csrf)
    e = entries[idx]
    keys = "\n".join(str(k) for k in (e.get("keys") or []))
    title = e.get("title") or ""
    answer = e.get("answer") or ""
    body = (
        f"<h1>Изменить запись #{idx + 1}</h1>"
        '<div class="card"><form method="post" action="/qa/edit">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        f'<input type="hidden" name="i" value="{idx}">'
        f"<label>Заголовок</label><input type=text name=title value=\"{html.escape(str(title))}\">"
        "<label>Ключи (по одному на строку)</label>"
        f"<textarea name=keys>{html.escape(keys)}</textarea>"
        f"<label>Ответ</label><textarea name=answer>{html.escape(str(answer))}</textarea>"
        '<div style="margin-top:12px"><button type=submit>Сохранить</button> '
        '<a class="btn" style="background:#374151" href="/qa">Отмена</a></div>'
        "</form></div>"
    )
    return _layout(state, body, title="Изменить ответ", flash=flash, csrf=csrf)


def _fixes_list(state: _PanelState, csrf: str, flash: str = "") -> bytes:
    fixes = _load_fix_store()
    rows = []
    for k, v in fixes.items():
        rows.append(
            "<tr>"
            f"<td>{html.escape(k)}</td>"
            f'<td><a href="{html.escape(v)}" target=_blank rel=noopener>{html.escape(v)}</a></td>'
            "<td class=right>"
            f'<form class="inline-form" method="post" action="/fixes/delete" '
            f'onsubmit="return confirm(\'Удалить фикс?\')">'
            f'<input type="hidden" name="csrf" value="{csrf}">'
            f'<input type="hidden" name="key" value="{html.escape(k)}">'
            f'<button class="btn btn-sm btn-danger" type=submit>Удал.</button></form>'
            "</td></tr>"
        )
    table = (
        "<table><tr><th>Запрос (нормализованный)</th><th>URL</th><th></th></tr>"
        + ("".join(rows) or '<tr><td colspan=3 class=muted>Пока пусто</td></tr>')
        + "</table>"
    )
    add_form = (
        '<div class="card"><h2>Добавить фикс</h2>'
        '<p class="muted">Запрос будет нормализован (нижний регистр). Если текст вопроса совпадёт — бот отдаст указанный URL.</p>'
        '<form method="post" action="/fixes/add">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        "<label>Текст запроса</label><input type=text name=query>"
        "<label>URL ответа</label><input type=text name=url>"
        '<div style="margin-top:12px"><button type=submit>Добавить</button></div>'
        "</form></div>"
    )
    body = f"<h1>Фиксы ссылок</h1>{add_form}<div class=card>{table}</div>"
    return _layout(state, body, title="Фиксы ссылок", flash=flash, csrf=csrf)


def _tail_lines(path: Path, limit: int, needle: str = "") -> list[str]:
    try:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        return [f"(ошибка чтения лога: {e})"]
    if needle:
        nl = needle.lower()
        lines = [ln for ln in lines if nl in ln.lower()]
    return [ln.rstrip("\n") for ln in lines[-limit:]]


def _logs_page(state: _PanelState, query: str, limit: int, csrf: str = "", flash: str = "") -> bytes:
    path = project_repo_root() / "logs" / "bot.log"
    lines = _tail_lines(path, limit, query)
    content = html.escape("\n".join(lines)) or "(пусто)"
    body = (
        "<h1>Логи решений</h1>"
        '<div class="card"><form method="get" action="/logs">'
        '<div style="display:flex; gap:10px; align-items:end; flex-wrap:wrap">'
        f'<div style="flex:1; min-width:200px"><label>Фильтр (подстрока)</label>'
        f'<input type=text name=q value="{html.escape(query)}" placeholder="напр. skip  или  reason="></div>'
        f'<div style="width:120px"><label>Строк</label><input type=number name=n value="{limit}"></div>'
        '<div><button type=submit>Показать</button></div>'
        "</div></form>"
        f'<p class="muted">Файл: {html.escape(str(path))}</p>'
        f"<pre class=logs>{content}</pre></div>"
    )
    return _layout(state, body, title="Логи", flash=flash, csrf=csrf)


# ------------------------- Настройки (.env) -------------------------

# Группы полей: (заголовок, [(ENV_KEY, подпись, тип)]). Тип: "bool" | "int" | "str" | "secret".
# TELEGRAM_BOT_TOKEN намеренно отсутствует — токен через панель не меняем.
_CONFIG_SECTIONS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Вики и индексация", [
        ("WIKI_BASE_URL", "Базовый URL вики", "str"),
        ("WIKI_SITEMAP_URL", "Sitemap URL", "str"),
        ("WIKI_REFRESH_HOURS", "Свежесть кэша, ч", "int"),
        ("WIKI_MAX_PAGES", "Лимит страниц (0 = без лимита)", "int"),
        ("INDEX_BATCH_SIZE", "Страниц за шаг", "int"),
        ("INDEX_INTERVAL_SECONDS", "Интервал шага, с", "int"),
        ("AUTO_TUNE_INDEXER", "Автоподстройка интервала", "bool"),
        ("INDEX_INTERVAL_MIN_SECONDS", "Мин. интервал, с", "int"),
        ("INDEX_INTERVAL_MAX_SECONDS", "Макс. интервал, с", "int"),
        ("MEMORY_LIMIT_MB", "Лимит памяти, МиБ (0 = без)", "int"),
        ("CACHE_PATH", "Путь кэша индекса", "str"),
        ("STATE_PATH", "Путь файла состояния", "str"),
    ]),
    ("Ответы и поиск", [
        ("MIN_SCORE", "Порог совпадения (0..100)", "int"),
        ("TOP_K", "Сколько совпадений показывать", "int"),
        ("QUESTIONS_ONLY", "Отвечать только на вопросы", "bool"),
        ("REQUIRE_TRIGGER", "Только при обращении к боту", "bool"),
        ("RU_LAYER_ENABLED", "Русский слой", "bool"),
    ]),
    ("Уточняющие вопросы", [
        ("CLARIFY_ENABLED", "Включены", "bool"),
        ("CLARIFY_MIN_SCORE", "Мин. score для уточнения", "int"),
        ("CLARIFY_COOLDOWN_SECONDS", "Кулдаун, с", "int"),
        ("CLARIFY_CORRECTION_MAX", "Макс. поправок модели", "int"),
        ("CLARIFY_CORRECTION_TTL_SECONDS", "Окно поправок, с", "int"),
    ]),
    ("Антиспам", [
        ("COOLDOWN_SECONDS", "Пауза между ответами, с", "int"),
        ("MAX_REPLIES_PER_MINUTE", "Ответов в минуту", "int"),
        ("DUPLICATE_WINDOW_SECONDS", "Окно дублей ссылки, с", "int"),
    ]),
    ("Где работать", [
        ("ALLOWED_CHAT_IDS", "Разрешённые чаты (id через запятую)", "str"),
        ("ALLOWED_TOPIC_IDS", "Разрешённые темы (через запятую)", "str"),
        ("REQUIRE_CAN_REPLY", "Проверять право писать в чат", "bool"),
        ("REPLY_ACCESS_CACHE_SECONDS", "TTL кэша прав, с", "int"),
        ("EPHEMERAL_EXEMPT_CHAT_IDS", "Не автоудалять команды (чаты)", "str"),
        ("DEVELOPER_USER_IDS", "Разработчики (user_id через запятую)", "str"),
    ]),
    ("Логи и уведомления", [
        ("LOG_ALL_MESSAGES", "Логировать все сообщения", "bool"),
        ("LOG_DECISIONS", "Логировать решения", "bool"),
        ("NOTIFY_ON_INDEX_DONE", "Уведомлять о конце индексации", "bool"),
        ("NOTIFY_CHAT_ID", "Чат уведомления индексации", "str"),
        ("NOTIFY_MENTION", "Упоминание в уведомлении", "str"),
        ("REPLY_REVIEW_MENTION", "Упоминание ревьюера в ответах", "str"),
        ("OPS_NOTIFY_CHAT_ID", "Служебный чат (логи/ошибки)", "str"),
    ]),
    # Веб-панель намеренно скрыта из редактора — меняется только через .env на сервере.
]

_TRUTHY = {"1", "true", "yes", "y", "on"}


def _is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except (TypeError, ValueError):
        return False


def _env_file_path() -> Path:
    return project_repo_root() / ".env"


def _read_env_values(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    if not path.exists():
        return vals
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        vals[k.strip()] = v.strip()
    return vals


def _write_env_values(path: Path, updates: dict[str, str]) -> None:
    """Обновляет значения существующих ключей, новые дописывает в конец. Комментарии сохраняются."""
    raw = path.read_bytes() if path.exists() else b""
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8", errors="replace") if raw else ""
    lines = text.split("\n")
    lines = [ln.rstrip("\r") for ln in lines]
    seen: set[str] = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.split("=", 1)[0].strip()
            if key in updates:
                lines[i] = f"{key}={updates[key]}"
                seen.add(key)
    extra = [k for k in updates if k not in seen]
    if extra:
        if lines and lines[-1].strip() != "":
            lines.append("")
        for k in extra:
            lines.append(f"{k}={updates[k]}")
    # убираем возможный финальный пустой элемент, чтобы не плодить пустые строки
    while len(lines) > 1 and lines[-1] == "":
        lines.pop()
    # Пишем байтами, чтобы текстовый режим не транслировал \n повторно (иначе \r\r\n на Windows).
    path.write_bytes((newline.join(lines) + newline).encode("utf-8"))


def _current_config_value(key: str, ftype: str, env_vals: dict[str, str], settings: Any) -> str:
    """Текущее значение: из .env, иначе из активных настроек (для корректных дефолтов)."""
    if key in env_vals:
        return env_vals[key]
    val = getattr(settings, key.lower(), None)
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (set, frozenset)):
        return ",".join(str(x) for x in sorted(val))
    return str(val)


def _config_page(state: _PanelState, csrf: str, flash: str = "") -> bytes:
    env_vals = _read_env_values(_env_file_path())
    st = state.settings
    sections_html = []
    for title, fields in _CONFIG_SECTIONS:
        rows = []
        for key, label, ftype in fields:
            cur = "" if ftype == "secret" else _current_config_value(key, ftype, env_vals, st)
            if ftype == "bool":
                checked = "checked" if cur.lower() in _TRUTHY else ""
                field = (
                    f'<input type="checkbox" name="{key}" value="true" {checked} '
                    'style="width:auto;margin-right:8px">'
                )
                rows.append(
                    f'<div style="margin:8px 0"><label style="display:inline">'
                    f"{field}{html.escape(label)} <span class=muted>({key})</span></label></div>"
                )
            else:
                itype = "password" if ftype == "secret" else ("number" if ftype == "int" else "text")
                ph = "оставьте пустым — без изменений" if ftype == "secret" else ""
                rows.append(
                    f"<label>{html.escape(label)} <span class=muted>({key})</span></label>"
                    f'<input type="{itype}" name="{key}" value="{html.escape(cur)}" placeholder="{ph}">'
                )
        sections_html.append(f'<div class="card"><h2>{html.escape(title)}</h2>{"".join(rows)}</div>')

    body = (
        "<h1>Настройки</h1>"
        '<p class="muted">Меняются значения в файле <code>.env</code>. '
        "Токен бота здесь не редактируется. Часть параметров (порт/адрес панели, индексация, лимиты) "
        "применяется только <b>после перезапуска</b>.</p>"
        '<form method="post" action="/config/save">'
        f'<input type="hidden" name="csrf" value="{csrf}">'
        + "".join(sections_html)
        + '<div class="card" style="position:sticky;bottom:0">'
        '<button type="submit" name="action" value="save">Сохранить</button> '
        '<button type="submit" name="action" value="save_restart" class="btn" '
        "style=\"background:#b45309\" "
        "onclick=\"return confirm('Сохранить и перезапустить бота?')\">Сохранить и перезапустить</button>"
        '</div></form>'
    )
    return _layout(state, body, title="Настройки", flash=flash, csrf=csrf)


# ------------------------- HTTP handler -------------------------


def _make_handler(state: _PanelState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "KobraPanel/1.0"
        _csrf = ""

        # тише в консоли — пишем свои строки через logging при желании
        def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
            return

        # --- утилиты ---
        def _client_ip(self) -> str:
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                return xff.split(",")[0].strip()
            return self.client_address[0] if self.client_address else "?"

        def _session(self) -> tuple[str | None, dict[str, Any] | None]:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie[_COOKIE_NAME].value if _COOKIE_NAME in cookie else None
            return token, state.get_session(token)

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            data = parse_qs(raw, keep_blank_values=True)
            return {k: (v[0] if v else "") for k, v in data.items()}

        def _send(
            self,
            body: bytes,
            *,
            status: int = 200,
            content_type: str = "text/html; charset=utf-8",
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass

        def _redirect(self, location: str, *, cookie: str | None = None) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _require_auth(self) -> dict[str, Any] | None:
            _token, sess = self._session()
            if sess is None:
                self._redirect("/login")
                return None
            # csrf токен текущей сессии — на этом запросе (инстанс Handler создаётся на каждый запрос)
            self._csrf = sess["csrf"]
            return sess

        def _check_csrf(self, form: dict[str, str], sess: dict[str, Any]) -> bool:
            return secrets.compare_digest(form.get("csrf", ""), sess.get("csrf", ""))

        # --- GET ---
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            qs = parse_qs(parsed.query)

            if path == "/login":
                _t, sess = self._session()
                if sess is not None:
                    self._redirect("/")
                    return
                self._send(_login_page(state))
                return
            if path == "/logout":
                token, _ = self._session()
                state.drop_session(token)
                expire = f"{_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
                self._redirect("/login", cookie=expire)
                return
            if path == "/tg-auth":
                # Telegram может отдавать данные и через GET (data-auth-url).
                self._handle_tg_auth({k: (v[0] if v else "") for k, v in qs.items()})
                return
            if path == "/bot-login/status":
                code = (qs.get("code") or [""])[0]
                status = get_code_status(state.application, code) if (state.application and code) else "expired"
                self._send(status.encode("utf-8"), content_type="text/plain; charset=utf-8")
                return
            if path == "/bot-login/finish":
                self._bot_login_finish((qs.get("code") or [""])[0])
                return

            sess = self._require_auth()
            if sess is None:
                return

            if path == "/":
                self._send(_dashboard(state, self._csrf))
            elif path == "/qa":
                self._send(_qa_list(state, self._csrf))
            elif path == "/qa/edit":
                try:
                    idx = int((qs.get("i") or ["-1"])[0])
                except ValueError:
                    idx = -1
                self._send(_qa_edit_page(state, idx, self._csrf))
            elif path == "/fixes":
                self._send(_fixes_list(state, self._csrf))
            elif path == "/logs":
                q = (qs.get("q") or [""])[0]
                try:
                    n = max(1, min(2000, int((qs.get("n") or ["300"])[0])))
                except ValueError:
                    n = 300
                self._send(_logs_page(state, q, n, self._csrf))
            elif path == "/config":
                self._send(_config_page(state, self._csrf))
            else:
                self._send(_layout(state, "<h1>404</h1><p>Страница не найдена.</p>"), status=404)

        # --- POST ---
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/login":
                self._handle_login()
                return
            if path == "/tg-auth":
                self._handle_tg_auth(self._read_form())
                return
            if path == "/bot-login/new":
                self._bot_login_new()
                return

            sess = self._require_auth()
            if sess is None:
                return
            form = self._read_form()
            if not self._check_csrf(form, sess):
                self._send(_layout(state, "<h1>Ошибка CSRF</h1><p>Обновите страницу и повторите.</p>"), status=400)
                return

            if path == "/qa/add":
                self._qa_add(form)
            elif path == "/qa/edit":
                self._qa_edit(form)
            elif path == "/qa/delete":
                self._qa_delete(form)
            elif path == "/fixes/add":
                self._fixes_add(form)
            elif path == "/fixes/delete":
                self._fixes_delete(form)
            elif path == "/config/save":
                self._config_save(form)
            elif path == "/update/check":
                self._update_check()
            elif path == "/update/run":
                self._update_run()
            elif path == "/replies/flag":
                self._replies_flag(form)
            elif path == "/bad-answers/delete":
                self._bad_answers_delete(form)
            elif path == "/missed-questions/delete":
                self._missed_questions_delete(form)
            elif path == "/missed-questions/clear":
                self._missed_questions_clear(form)
            else:
                self._send(_layout(state, "<h1>404</h1>"), status=404)

        # --- обработчики действий ---
        def _handle_login(self) -> None:
            ip = self._client_ip()
            if state.login_blocked(ip):
                self._send(_login_page(state, error="Слишком много попыток. Подождите 5 минут."), status=429)
                return
            form = self._read_form()
            user = form.get("username", "")
            pwd = form.get("password", "")
            exp_user = state.settings.panel_username
            exp_pwd = state.settings.panel_password
            ok = bool(exp_pwd) and secrets.compare_digest(user, exp_user) and secrets.compare_digest(pwd, exp_pwd)
            if not ok:
                state.record_login_fail(ip)
                log.warning("panel: неудачный вход с %s", ip)
                self._send(_login_page(state, error="Неверный логин или пароль."), status=401)
                return
            state.clear_login_fails(ip)
            token, _csrf = state.new_session(user=exp_user)
            log.info("panel: вход по паролю с %s", ip)
            self._redirect("/", cookie=self._session_cookie(token))

        def _session_cookie(self, token: str) -> str:
            ttl = max(60, int(getattr(state.settings, "panel_session_ttl_seconds", 86400)))
            return f"{_COOKIE_NAME}={token}; Path=/; Max-Age={ttl}; HttpOnly; SameSite=Lax"

        def _handle_tg_auth(self, data: dict[str, str]) -> None:
            ip = self._client_ip()
            st = state.settings
            chat_id = getattr(st, "panel_admin_chat_id", None)
            token_str = getattr(st, "telegram_bot_token", "")
            if not getattr(st, "panel_tg_login", False) or not chat_id or not token_str:
                self._send(_login_page(state, error="Вход через Telegram не настроен."), status=403)
                return
            if state.login_blocked(ip):
                self._send(_login_page(state, error="Слишком много попыток. Подождите 5 минут."), status=429)
                return
            ok, why = _verify_telegram_auth(data, token_str)
            if not ok:
                state.record_login_fail(ip)
                log.warning("panel: tg-вход отклонён (%s) с %s", why, ip)
                self._send(_login_page(state, error=f"Telegram: {why}"), status=401)
                return
            try:
                uid = int(data.get("id", "0") or 0)
            except ValueError:
                uid = 0
            admin_ids, err = state.admin_ids(token_str, int(chat_id))
            if err:
                log.warning("panel: проверка админов не удалась: %s", err)
                self._send(_login_page(state, error=err), status=502)
                return
            if uid not in (admin_ids or set()):
                state.record_login_fail(ip)
                log.warning("panel: tg-вход отклонён, не админ uid=%s", uid)
                self._send(
                    _login_page(state, error="Вы не администратор нужной группы — доступ запрещён."),
                    status=403,
                )
                return
            state.clear_login_fails(ip)
            uname = data.get("username", "")
            label = f"@{uname}" if uname else (data.get("first_name") or str(uid))
            token, _csrf = state.new_session(user=label)
            log.info("panel: tg-вход uid=%s %s с %s", uid, label, ip)
            self._redirect("/", cookie=self._session_cookie(token))

        def _bot_login_new(self) -> None:
            st = state.settings
            bd = state.application.bot_data if state.application else {}
            bot_user = bd.get("bot_username")
            if not (getattr(st, "panel_tg_login", False) and getattr(st, "panel_admin_chat_id", None)):
                self._send(_login_page(state, error="Вход через Telegram не настроен."), status=403)
                return
            if not bot_user:
                self._send(_login_page(state, error="Бот ещё запускается, попробуйте через пару секунд."), status=503)
                return
            nonce = secrets.token_urlsafe(24)
            code = create_login_code(state.application, nonce)
            ttl = 600
            cookie = f"panel_login_nonce={nonce}; Path=/; Max-Age={ttl}; HttpOnly; SameSite=Lax"
            self._send(_bot_login_wait_page(str(bot_user), code), headers={"Set-Cookie": cookie})

        def _bot_login_finish(self, code: str) -> None:
            if not code or state.application is None:
                self._send(_login_page(state, error="Не удалось завершить вход."), status=400)
                return
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            nonce = cookie["panel_login_nonce"].value if "panel_login_nonce" in cookie else ""
            info, err = consume_authorized(state.application, code, nonce)
            if err or not info:
                msg = {
                    "denied": "Доступ запрещён: вы не администратор группы.",
                    "expired": "Срок действия истёк, начните вход заново.",
                    "nonce": "Вход нужно завершать в том же браузере, где он начат.",
                    "pending": "Вход ещё не подтверждён в боте.",
                    "consumed": "Эта ссылка входа уже использована.",
                }.get(err or "", "Не удалось завершить вход.")
                self._send(_login_page(state, error=msg), status=403)
                return
            token, _csrf = state.new_session(user=str(info.get("user") or ""))
            clear_nonce = "panel_login_nonce=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", self._session_cookie(token))
            self.send_header("Set-Cookie", clear_nonce)
            self.send_header("Content-Length", "0")
            self.end_headers()
            log.info("panel: вход через бота %s", info.get("user"))

        def _flash(self, ok: bool, msg: str) -> str:
            cls = "ok" if ok else "err"
            return f'<div class="flash {cls}">{html.escape(msg)}</div>'

        def _git_params(self) -> tuple[str, str, bool]:
            st = state.settings
            return (
                getattr(st, "git_autopull_remote", "origin") or "origin",
                getattr(st, "git_autopull_branch", "master") or "master",
                bool(getattr(st, "git_autopull_hard_reset", True)),
            )

        def _update_check(self) -> None:
            remote, branch, _hard = self._git_params()
            try:
                local, rhash, avail, err = git_ping_compare_with_remote(
                    repo=project_repo_root(), remote=remote, branch=branch
                )
            except Exception as e:  # noqa: BLE001
                self._send(_dashboard(state, self._csrf, flash=self._flash(False, f"Ошибка проверки: {e}")))
                return
            if err:
                msg, ok = f"Не удалось проверить: {err}", False
            elif avail:
                msg, ok = (
                    f"Есть обновление: {(local or '')[:8]} → {(rhash or '')[:8]}. "
                    "Нажмите «Обновить», чтобы применить.",
                    True,
                )
            else:
                msg, ok = "Установлена последняя версия.", True
            self._send(_dashboard(state, self._csrf, flash=self._flash(ok, msg)))

        def _update_run(self) -> None:
            remote, branch, hard = self._git_params()
            try:
                updated, gmsg = git_sync_from_remote(
                    repo=project_repo_root(), remote=remote, branch=branch, hard_reset=hard
                )
            except Exception as e:  # noqa: BLE001
                self._send(_dashboard(state, self._csrf, flash=self._flash(False, f"Ошибка обновления: {e}")))
                return
            if not updated:
                self._send(_dashboard(state, self._csrf, flash=self._flash(True, f"Обновление не требуется: {gmsg}")))
                return
            ok, rmsg = self._trigger_restart()
            self._send(_dashboard(state, self._csrf, flash=self._flash(ok, f"Обновлено: {gmsg}. {rmsg}")))

        def _trigger_restart(self) -> tuple[bool, str]:
            app = state.application
            loop = app.bot_data.get("main_loop") if app else None
            if app is None or loop is None:
                return False, "перезапуск недоступен (нет ссылки на процесс бота)"
            try:
                coro = schedule_restart_after_pull(
                    application=app,
                    git_pull_restart_state=app.bot_data.setdefault(
                        "git_pull_restart_state", {"action": "none", "cmd": ""}
                    ),
                    restart_command=getattr(state.settings, "git_restart_command", None),
                    log_tag="panel",
                )
                asyncio.run_coroutine_threadsafe(coro, loop)
                return True, "перезапуск запущен"
            except Exception as e:  # noqa: BLE001
                return False, f"не удалось запустить перезапуск: {e}"

        def _config_save(self, form: dict[str, str]) -> None:
            env_vals = _read_env_values(_env_file_path())
            updates: dict[str, str] = {}
            errors: list[str] = []
            for _title, fields in _CONFIG_SECTIONS:
                for key, label, ftype in fields:
                    if ftype == "secret":
                        new = form.get(key, "").strip()
                        if new:
                            updates[key] = new
                        continue
                    cur = _current_config_value(key, ftype, env_vals, state.settings)
                    if ftype == "bool":
                        new = "true" if form.get(key, "").lower() in _TRUTHY else "false"
                        if new != (cur.lower() if cur else "false"):
                            updates[key] = new
                        continue
                    new = form.get(key, "").strip()
                    if ftype == "int" and new and not _is_int(new):
                        errors.append(f"«{label}» ({key}): нужно целое число")
                        continue
                    if new != cur:
                        updates[key] = new
            if errors:
                self._send(_config_page(state, self._csrf, flash=self._flash(False, "; ".join(errors))), status=400)
                return
            if not updates:
                self._send(_config_page(state, self._csrf, flash=self._flash(True, "Изменений нет")))
                return
            try:
                _write_env_values(_env_file_path(), updates)
            except Exception as e:  # noqa: BLE001
                self._send(_config_page(state, self._csrf, flash=self._flash(False, f"Ошибка записи .env: {e}")))
                return
            log.info("panel: обновлён .env (%d ключей)", len(updates))
            changed = ", ".join(sorted(updates))
            if form.get("action") == "save_restart":
                ok, msg = self._trigger_restart()
                self._send(
                    _config_page(
                        state, self._csrf,
                        flash=self._flash(ok, f"Сохранено ({changed}). {msg}"),
                    )
                )
                return
            self._send(
                _config_page(
                    state, self._csrf,
                    flash=self._flash(True, f"Сохранено ({changed}). Применится после перезапуска."),
                )
            )

        def _push_qa_if_enabled(self) -> str:
            if not getattr(state.settings, "manual_qa_git_push", False):
                return ""
            try:
                pushed, info = try_git_push_manual_qa()
                return f" · git: {info}" if pushed else f" · git ошибка: {info}"
            except Exception as e:  # noqa: BLE001
                return f" · git исключение: {e}"

        def _refresh_qa_live(self) -> list[dict[str, Any]]:
            entries = load_manual_qa_store()
            if state.application is not None:
                state.application.bot_data["manual_qa_entries"] = entries
            return entries

        def _qa_add(self, form: dict[str, str]) -> None:
            keys = [ln.strip() for ln in form.get("keys", "").splitlines() if ln.strip()]
            entries = load_manual_qa_store()
            ok, msg = add_manual_qa_entry(
                entries=entries,
                raw_keys=keys,
                answer=form.get("answer", ""),
                title=form.get("title", ""),
            )
            if ok:
                self._refresh_qa_live()
                msg += self._push_qa_if_enabled()
            self._send(_qa_list(state, self._csrf, flash=self._flash(ok, msg)))

        def _qa_edit(self, form: dict[str, str]) -> None:
            try:
                idx = int(form.get("i", "-1"))
            except ValueError:
                idx = -1
            entries = load_manual_qa_store()
            if idx < 0 or idx >= len(entries):
                self._send(_qa_list(state, self._csrf, flash=self._flash(False, "Запись не найдена")))
                return
            keys = [_norm_text(ln) for ln in form.get("keys", "").splitlines() if ln.strip()]
            keys = [k for k in keys if k]
            answer = form.get("answer", "").strip()
            title = form.get("title", "").strip() or (keys[0][:80] if keys else "manual")
            if not keys or not answer:
                self._send(_qa_edit_page(state, idx, self._csrf, flash=self._flash(False, "Нужны хотя бы один ключ и текст ответа")))
                return
            entries[idx] = {"keys": keys, "answer": answer, "title": title, "ts": time.time()}
            save_manual_qa_store(entries)
            self._refresh_qa_live()
            info = self._push_qa_if_enabled()
            self._send(_qa_list(state, self._csrf, flash=self._flash(True, "Сохранено" + info)))

        def _qa_delete(self, form: dict[str, str]) -> None:
            try:
                idx = int(form.get("i", "-1"))
            except ValueError:
                idx = -1
            entries = load_manual_qa_store()
            ok, msg = delete_manual_qa_by_index(entries=entries, one_based=idx + 1)
            if ok:
                self._refresh_qa_live()
                msg += self._push_qa_if_enabled()
            self._send(_qa_list(state, self._csrf, flash=self._flash(ok, msg)))

        def _fixes_add(self, form: dict[str, str]) -> None:
            query = _norm_text(form.get("query", ""))
            url = form.get("url", "").strip()
            if not query or not url:
                self._send(_fixes_list(state, self._csrf, flash=self._flash(False, "Нужны и запрос, и URL")))
                return
            fixes = _load_fix_store()
            fixes[query] = url
            _save_fix_store(fixes)
            if state.application is not None:
                state.application.bot_data["fix_store"] = fixes
            self._send(_fixes_list(state, self._csrf, flash=self._flash(True, "Фикс добавлен")))

        def _fixes_delete(self, form: dict[str, str]) -> None:
            key = form.get("key", "")
            fixes = _load_fix_store()
            existed = fixes.pop(key, None) is not None
            _save_fix_store(fixes)
            if state.application is not None:
                state.application.bot_data["fix_store"] = fixes
            msg = "Фикс удалён" if existed else "Такого фикса нет"
            self._send(_fixes_list(state, self._csrf, flash=self._flash(existed, msg)))

        def _replies_flag(self, form: dict[str, str]) -> None:
            """Отмечает ответ из ленты как ошибочный, удаляет из ленты и сохраняет в bad_answers.json."""
            try:
                idx = int(form.get("i", "-1"))
            except ValueError:
                idx = -1
            replies: list[dict] = (
                (state.application.bot_data.get("recent_replies") or [])
                if state.application else []
            )
            if idx < 0 or idx >= len(replies):
                self._send(_dashboard(state, self._csrf, flash=self._flash(False, "Запись не найдена")))
                return
            r = replies[idx]
            note = form.get("note", "").strip()
            flag_bad_answer(
                question=str(r.get("question", "")),
                answer=str(r.get("answer", "")),
                url=str(r.get("url", "")),
                source=str(r.get("source", "")),
                note=note,
            )
            # Убираем из ленты — повторная отметка невозможна, сохраняем на диск
            replies.pop(idx)
            if state.application is not None:
                save_recent_replies(state.application.bot_data)
            # пушим, если включено
            push_info = ""
            if getattr(state.settings, "manual_qa_git_push", False):
                try:
                    pushed, pmsg = try_git_push_bad_answers()
                    push_info = f" · git: {pmsg}" if pushed else f" · git ошибка: {pmsg}"
                except Exception as e:  # noqa: BLE001
                    push_info = f" · git исключение: {e}"
            self._send(_dashboard(state, self._csrf,
                                  flash=self._flash(True, f"Ответ отмечен как ошибочный{push_info}")))

        def _bad_answers_delete(self, form: dict[str, str]) -> None:
            """Удаляет обработанную запись из bad_answers.json."""
            try:
                idx = int(form.get("i", "-1"))
            except ValueError:
                idx = -1
            ok, msg = delete_bad_answer(idx=idx)
            if ok and getattr(state.settings, "manual_qa_git_push", False):
                try:
                    pushed, pmsg = try_git_push_bad_answers()
                    msg += f" · git: {pmsg}" if pushed else f" · git ошибка: {pmsg}"
                except Exception as e:  # noqa: BLE001
                    msg += f" · git исключение: {e}"
            self._send(_dashboard(state, self._csrf, flash=self._flash(ok, msg)))

        def _missed_questions_delete(self, form: dict[str, str]) -> None:
            """Удаляет одну запись из missed_questions.json."""
            try:
                idx = int(form.get("i", "-1"))
            except ValueError:
                idx = -1
            ok, msg = delete_missed_question(idx=idx)
            self._send(_dashboard(state, self._csrf, flash=self._flash(ok, msg)))

        def _missed_questions_clear(self, form: dict[str, str]) -> None:  # noqa: ARG002
            """Очищает весь список missed_questions.json."""
            count = clear_missed_questions()
            self._send(_dashboard(state, self._csrf,
                                  flash=self._flash(True, f"Удалено {count} записей")))

    return Handler


def start_web_panel(application: Any, settings: Any) -> ThreadingHTTPServer | None:
    """Запускает веб-панель в фоновом потоке. Возвращает сервер или None (если выключена)."""
    if not getattr(settings, "panel_enabled", False):
        return None
    has_pwd = bool(getattr(settings, "panel_password", ""))
    has_tg = bool(
        getattr(settings, "panel_tg_login", False)
        and getattr(settings, "panel_admin_chat_id", None)
        and getattr(settings, "telegram_bot_token", "")
    )
    if not (has_pwd or has_tg):
        log.warning(
            "Веб-панель включена, но не настроен вход: задайте PANEL_PASSWORD "
            "и/или оставьте PANEL_TG_LOGIN с PANEL_ADMIN_CHAT_ID. Панель не запущена."
        )
        return None

    state = _PanelState(application, settings)
    handler = _make_handler(state)
    host = getattr(settings, "panel_host", "0.0.0.0")
    port = int(getattr(settings, "panel_port", 8080))
    try:
        httpd = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        log.error("Не удалось запустить веб-панель на %s:%s — %s", host, port, e)
        return None
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, name="web_panel", daemon=True)
    t.start()
    log.info("Веб-панель запущена: http://%s:%s (логин: %s)", host, port, settings.panel_username)
    return httpd
