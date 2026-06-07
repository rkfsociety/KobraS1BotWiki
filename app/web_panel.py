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

import html
import logging
import os
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.bot.git_autopull import project_repo_root
from app.bot.manual_qa import (
    add_manual_qa_entry,
    delete_manual_qa_by_index,
    load_manual_qa_store,
    save_manual_qa_store,
    try_git_push_manual_qa,
)
from app.bot.stores import _load_fix_store, _norm_text, _save_fix_store

log = logging.getLogger(__name__)

_COOKIE_NAME = "panel_session"


class _PanelState:
    """Общее состояние панели: ссылка на бота, настройки, сессии."""

    def __init__(self, application: Any, settings: Any) -> None:
        self.application = application
        self.settings = settings
        self.start_time = time.time()
        # token -> {"exp": float, "csrf": str}
        self.sessions: dict[str, dict[str, Any]] = {}
        # ip -> [timestamps] неудачных попыток входа
        self.login_fails: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    # --- сессии ---
    def new_session(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(16)
        ttl = max(60, int(getattr(self.settings, "panel_session_ttl_seconds", 86400)))
        with self.lock:
            self.sessions[token] = {"exp": time.time() + ttl, "csrf": csrf}
            self._gc_locked()
        return token, csrf

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
"""


def _layout(state: _PanelState, body: str, *, title: str = "Панель бота", flash: str = "") -> bytes:
    bot = state.application.bot_data.get("bot_username") if state.application else None
    nav = (
        '<nav>'
        '<a href="/">Дашборд</a>'
        '<a href="/qa">Ручные ответы</a>'
        '<a href="/fixes">Фиксы ссылок</a>'
        '<a href="/logs">Логи</a>'
        '</nav>'
    )
    head = (
        '<header>'
        f'<span class="brand">🤖 {html.escape("@" + bot) if bot else "Бот"}</span>'
        f'{nav}'
        '<span class="spacer"></span>'
        '<a href="/logout">Выйти</a>'
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
    body = (
        '<div class="login-wrap"><div class="card">'
        '<h2>Вход в панель</h2>'
        f"{err}"
        '<form method="post" action="/login">'
        '<label>Логин</label><input type="text" name="username" autofocus>'
        '<label>Пароль</label><input type="password" name="password">'
        '<div style="margin-top:16px"><button type="submit">Войти</button></div>'
        '</form></div></div>'
    )
    page = (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>Вход</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>"
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


def _dashboard(state: _PanelState, flash: str = "") -> bytes:
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

    stats = (
        stat(doc_count, "страниц вики в индексе")
        + stat("готов" if index_done else "идёт…", "индексация")
        + stat(len(qa), "ручных ответов")
        + stat(len(fixes), "фиксов ссылок")
        + stat(len(codes), "кодов ошибок")
        + stat(_fmt_uptime(time.time() - state.start_time), "аптайм панели")
    )
    st = state.settings
    cfg_rows = "".join(
        f"<tr><td class=muted>{html.escape(k)}</td><td><code>{html.escape(str(v))}</code></td></tr>"
        for k, v in [
            ("MIN_SCORE", getattr(st, "min_score", "")),
            ("CLARIFY_MIN_SCORE", getattr(st, "clarify_min_score", "")),
            ("QUESTIONS_ONLY", getattr(st, "questions_only", "")),
            ("REQUIRE_TRIGGER", getattr(st, "require_trigger", "")),
            ("LOG_DECISIONS", getattr(st, "log_decisions", "")),
            ("MANUAL_QA_GIT_PUSH", getattr(st, "manual_qa_git_push", "")),
            ("PID", os.getpid()),
        ]
    )
    body = (
        "<h1>Дашборд</h1>"
        f'<div class="card"><div class="grid">{stats}</div></div>'
        '<div class="card kv"><h2>Конфигурация (только просмотр)</h2>'
        f"<table>{cfg_rows}</table>"
        '<p class="muted">Параметры задаются через переменные окружения / .env и применяются при запуске.</p>'
        "</div>"
    )
    return _layout(state, body, title="Дашборд", flash=flash)


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
        "<table><tr><th>#</th><th>Заголовок / ключи</th><th>Ответ</th><th></th></tr>"
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
    return _layout(state, body, title="Ручные ответы", flash=flash)


def _qa_edit_page(state: _PanelState, idx: int, csrf: str, flash: str = "") -> bytes:
    entries = load_manual_qa_store()
    if idx < 0 or idx >= len(entries):
        return _layout(state, "<h1>Запись не найдена</h1>", flash=flash)
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
    return _layout(state, body, title="Изменить ответ", flash=flash)


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
    return _layout(state, body, title="Фиксы ссылок", flash=flash)


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


def _logs_page(state: _PanelState, query: str, limit: int, flash: str = "") -> bytes:
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
    return _layout(state, body, title="Логи", flash=flash)


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

        def _send(self, body: bytes, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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

            sess = self._require_auth()
            if sess is None:
                return

            if path == "/":
                self._send(_dashboard(state))
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
                self._send(_logs_page(state, q, n))
            else:
                self._send(_layout(state, "<h1>404</h1><p>Страница не найдена.</p>"), status=404)

        # --- POST ---
        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/login":
                self._handle_login()
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
            token, _csrf = state.new_session()
            ttl = max(60, int(getattr(state.settings, "panel_session_ttl_seconds", 86400)))
            cookie = f"{_COOKIE_NAME}={token}; Path=/; Max-Age={ttl}; HttpOnly; SameSite=Lax"
            log.info("panel: вход выполнен с %s", ip)
            self._redirect("/", cookie=cookie)

        def _flash(self, ok: bool, msg: str) -> str:
            cls = "ok" if ok else "err"
            return f'<div class="flash {cls}">{html.escape(msg)}</div>'

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

    return Handler


def start_web_panel(application: Any, settings: Any) -> ThreadingHTTPServer | None:
    """Запускает веб-панель в фоновом потоке. Возвращает сервер или None (если выключена)."""
    if not getattr(settings, "panel_enabled", False):
        return None
    if not getattr(settings, "panel_password", ""):
        log.warning("Веб-панель включена, но PANEL_PASSWORD не задан — панель не запущена.")
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
