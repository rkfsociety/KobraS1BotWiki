"""Смоук-тесты встроенной веб-панели: вход, защита, страницы, CRUD ручных ответов."""
from __future__ import annotations

import http.client
import time
import types

import pytest

from app.web_panel import _CSS, _bot_stats_section, start_web_panel


class _StubApp:
    def __init__(self) -> None:
        self.bot_data: dict = {
            "bot_username": "TestBot",
            "wiki_index": types.SimpleNamespace(doc_count=42),
            "wiki_indexer": types.SimpleNamespace(is_done=lambda: True),
            "manual_qa_entries": [],
            "fix_store": {},
            "error_codes_catalog": {},
        }


class _StubSettings:
    panel_enabled = True
    panel_password = "secret"
    panel_username = "admin"
    panel_host = "127.0.0.1"
    panel_port = 0  # эфемерный порт
    panel_session_ttl_seconds = 3600
    panel_tg_login = True
    panel_admin_chat_id = -1003881305021
    telegram_bot_token = "123456:TESTTOKEN"
    min_score = 72
    clarify_min_score = 45
    questions_only = True
    require_trigger = True
    log_decisions = True
    manual_qa_git_push = False


@pytest.fixture()
def panel(monkeypatch, tmp_path):
    # Изолируем файл ручных ответов, чтобы тесты не трогали data/manual_qa.json в репозитории.
    qa_file = tmp_path / "manual_qa.json"
    monkeypatch.setattr("app.bot.manual_qa._manual_qa_path", lambda: qa_file)
    # Изолируем .env, чтобы тесты не трогали реальный файл в репозитории.
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"MIN_SCORE=72\nQUESTIONS_ONLY=true\nWIKI_BASE_URL=https://w\n")
    monkeypatch.setattr("app.web_panel._env_file_path", lambda: env_file)
    app = _StubApp()
    app.bot_data["_test_env_file"] = env_file
    srv = start_web_panel(app, _StubSettings())
    assert srv is not None
    time.sleep(0.1)
    port = srv.server_address[1]
    yield app, port
    srv.shutdown()


def _conn(port: int) -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", port, timeout=5)


def _login(c: http.client.HTTPConnection) -> str:
    c.request(
        "POST",
        "/login",
        "username=admin&password=secret",
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    r = c.getresponse()
    cookie = r.getheader("Set-Cookie")
    r.read()
    assert cookie
    return cookie.split(";")[0]


def test_disabled_when_no_auth_method():
    # Ни пароля, ни TG-входа — панель не запускается.
    class Off(_StubSettings):
        panel_password = ""
        panel_tg_login = False
        panel_admin_chat_id = None

    assert start_web_panel(_StubApp(), Off()) is None


def test_starts_with_tg_only():
    # Без пароля, но с TG-входом — панель запускается.
    class TgOnly(_StubSettings):
        panel_password = ""

    srv = start_web_panel(_StubApp(), TgOnly())
    assert srv is not None
    srv.shutdown()


def test_requires_auth(panel):
    _app, port = panel
    c = _conn(port)
    c.request("GET", "/")
    r = c.getresponse()
    assert r.status == 303
    assert r.getheader("Location") == "/login"
    r.read()


def test_bad_login_rejected(panel):
    _app, port = panel
    c = _conn(port)
    c.request(
        "POST",
        "/login",
        "username=admin&password=WRONG",
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    r = c.getresponse()
    assert r.status == 401
    r.read()


def test_dashboard_after_login(panel):
    _app, port = panel
    c = _conn(port)
    ck = _login(c)
    c.request("GET", "/", headers={"Cookie": ck})
    r = c.getresponse()
    body = r.read()
    assert r.status == 200
    assert b"42" in body  # счётчик страниц вики


def test_dashboard_activity_layout_is_responsive_without_horizontal_scrollbar():
    assert "@media (max-width: 1100px)" in _CSS
    assert ".monitor-layout { grid-template-columns: 1fr; }" in _CSS
    assert ".monitor-grid--2 { grid-template-columns: 1fr; }" in _CSS
    assert ".admin-summary-table { table-layout: fixed; }" in _CSS
    assert ".monitor-table-wrap { overflow-x: visible; }" in _CSS


def test_dashboard_uses_amber_circular_activity_cards():
    body = _bot_stats_section(
        [], [], [0, 1, 2, 3, 4, 5, 6, 7] + [0] * 16, [],
        {"bot_stats": {"total_answers": 12}, "admin_activity": {}},
    )
    assert 'class="circle-chart-grid"' in body
    assert 'class="circle donut-activity"' in body
    assert 'class="circle donut-health"' in body
    assert 'Активность чата' in body
    assert 'Индексация' in body
    assert ".circle-chart-grid" in _CSS
    assert "#f0c674" in _CSS


def test_csrf_required_for_mutations(panel):
    _app, port = panel
    c = _conn(port)
    ck = _login(c)
    c.request(
        "POST",
        "/qa/add",
        "title=x&keys=abc&answer=hi",
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 400  # нет csrf-токена
    r.read()


def test_qa_add_updates_live_bot_data(panel):
    app, port = panel
    c = _conn(port)
    ck = _login(c)
    # достаём csrf со страницы /qa
    c.request("GET", "/qa", headers={"Cookie": ck})
    r = c.getresponse()
    page = r.read().decode("utf-8")
    import re

    m = re.search(r'name="csrf" value="([^"]+)"', page)
    assert m
    csrf = m.group(1)
    from urllib.parse import urlencode

    payload = urlencode(
        {"csrf": csrf, "title": "Тест", "keys": "как печатать\nпечать совет", "answer": "Ответ"}
    )
    c.request(
        "POST",
        "/qa/add",
        payload,
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get
    r.read()
    # запись попала в живой bot_data без перезапуска
    entries = app.bot_data["manual_qa_entries"]
    assert any(e.get("title") == "Тест" for e in entries)


# ---------------- Telegram-вход ----------------


def _sign_tg(data: dict, token: str) -> dict:
    import hashlib
    import hmac

    d = {k: str(v) for k, v in data.items() if v != "" and v is not None}
    dcs = "\n".join(sorted(f"{k}={v}" for k, v in d.items()))
    secret = hashlib.sha256(token.encode()).digest()
    d["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return d


def test_verify_telegram_auth_valid_and_tampered():
    import time as _t

    from app.web_panel import _verify_telegram_auth

    token = "123456:TESTTOKEN"
    data = _sign_tg({"id": 111, "username": "adm", "auth_date": int(_t.time())}, token)
    ok, _ = _verify_telegram_auth(data, token)
    assert ok
    # подделка значения ломает подпись
    bad = dict(data, id="999")
    ok2, _ = _verify_telegram_auth(bad, token)
    assert not ok2
    # просроченный auth_date
    old = _sign_tg({"id": 111, "auth_date": int(_t.time()) - 999999}, token)
    ok3, _ = _verify_telegram_auth(old, token)
    assert not ok3


def test_tg_auth_admin_allowed(panel, monkeypatch):
    import time as _t
    from urllib.parse import urlencode

    app, port = panel
    monkeypatch.setattr(
        "app.web_panel._telegram_api",
        lambda *a, **k: {"ok": True, "result": [{"user": {"id": 111, "is_bot": False}}]},
    )
    data = _sign_tg({"id": 111, "username": "adm", "auth_date": int(_t.time())}, "123456:TESTTOKEN")
    c = _conn(port)
    c.request(
        "POST", "/tg-auth", urlencode(data), {"Content-Type": "application/x-www-form-urlencoded"}
    )
    r = c.getresponse()
    assert r.status == 303
    cookie = r.getheader("Set-Cookie")
    r.read()
    assert cookie
    ck = cookie.split(";")[0]
    c.request("GET", "/", headers={"Cookie": ck})
    r = c.getresponse()
    assert r.status == 200
    r.read()


def test_tg_auth_non_admin_rejected(panel, monkeypatch):
    import time as _t
    from urllib.parse import urlencode

    _app, port = panel
    monkeypatch.setattr(
        "app.web_panel._telegram_api",
        lambda *a, **k: {"ok": True, "result": [{"user": {"id": 111, "is_bot": False}}]},
    )
    data = _sign_tg({"id": 999, "username": "stranger", "auth_date": int(_t.time())}, "123456:TESTTOKEN")
    c = _conn(port)
    c.request(
        "POST", "/tg-auth", urlencode(data), {"Content-Type": "application/x-www-form-urlencoded"}
    )
    r = c.getresponse()
    assert r.status == 403
    r.read()


def test_tg_auth_bad_signature_rejected(panel):
    import time as _t
    from urllib.parse import urlencode

    _app, port = panel
    data = {"id": "111", "username": "adm", "auth_date": str(int(_t.time())), "hash": "deadbeef"}
    c = _conn(port)
    c.request(
        "POST", "/tg-auth", urlencode(data), {"Content-Type": "application/x-www-form-urlencoded"}
    )
    r = c.getresponse()
    assert r.status == 401
    r.read()


# ---------------- Вход через бота (без домена) ----------------


def _start_bot_login(port: int) -> tuple[str, str]:
    """POST /bot-login/new → (code, nonce_cookie)."""
    import re

    c = _conn(port)
    c.request("POST", "/bot-login/new", "", {"Content-Type": "application/x-www-form-urlencoded"})
    r = c.getresponse()
    assert r.status == 200
    cookie = r.getheader("Set-Cookie")
    body = r.read().decode("utf-8")
    assert cookie and "panel_login_nonce=" in cookie
    m = re.search(r'var code=("[^"]+")', body)
    assert m
    import json as _j

    code = _j.loads(m.group(1))
    return code, cookie.split(";")[0]


def test_bot_login_helpers_flow():
    from app.bot.panel_login import consume_authorized, create_login_code, get_code_status

    app = _StubApp()
    code = create_login_code(app, "nonceAAA")
    assert get_code_status(app, code) == "pending"
    # неподтверждённый код нельзя использовать
    info, err = consume_authorized(app, code, "nonceAAA")
    assert info is None and err == "pending"
    # бот подтвердил
    app.bot_data["panel_login_codes"][code].update(status="authorized", uid=111, user="@adm")
    assert get_code_status(app, code) == "authorized"
    # неверный nonce — отказ
    info, err = consume_authorized(app, code, "WRONG")
    assert info is None and err == "nonce"
    # верный nonce — успех, и повторно уже нельзя
    info, err = consume_authorized(app, code, "nonceAAA")
    assert info and info["uid"] == 111
    info2, err2 = consume_authorized(app, code, "nonceAAA")
    assert info2 is None and err2 == "consumed"


def test_bot_login_full_http_flow(panel):
    app, port = panel
    code, nonce_ck = _start_bot_login(port)
    # статус до подтверждения
    c = _conn(port)
    c.request("GET", f"/bot-login/status?code={code}")
    r = c.getresponse()
    assert r.read().decode() == "pending"
    # эмулируем подтверждение ботом
    app.bot_data["panel_login_codes"][code].update(status="authorized", uid=111, user="@adm")
    c.request("GET", f"/bot-login/status?code={code}")
    r = c.getresponse()
    assert r.read().decode() == "authorized"
    # finish без nonce-cookie → отказ
    c.request("GET", f"/bot-login/finish?code={code}")
    r = c.getresponse()
    assert r.status == 403
    r.read()
    # finish с правильным nonce → сессия
    code2, nonce_ck2 = _start_bot_login(port)
    app.bot_data["panel_login_codes"][code2].update(status="authorized", uid=111, user="@adm")
    c.request("GET", f"/bot-login/finish?code={code2}", headers={"Cookie": nonce_ck2})
    r = c.getresponse()
    assert r.status == 303
    set_cookie = r.getheader("Set-Cookie")
    r.read()
    assert set_cookie and "panel_session=" in set_cookie
    sess_ck = set_cookie.split(";")[0]
    c.request("GET", "/", headers={"Cookie": sess_ck})
    r = c.getresponse()
    assert r.status == 200
    r.read()


def test_cmd_start_admin_authorizes_code():
    import asyncio

    from telegram.constants import ChatMemberStatus

    from app.bot.panel_login import cmd_start, create_login_code, get_code_status

    app = _StubApp()
    app.bot_data["settings"] = _StubSettings()
    code = create_login_code(app, "nonceX")

    class _Msg:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text):
            self.replies.append(text)

    class _User:
        id = 111
        username = "adm"
        full_name = "Adm"

    class _Bot:
        async def get_chat_member(self, chat_id, user_id):
            return types.SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR)

    msg = _Msg()
    ctx = types.SimpleNamespace(
        args=[code], application=types.SimpleNamespace(bot_data=app.bot_data), bot=_Bot()
    )
    upd = types.SimpleNamespace(effective_message=msg, effective_user=_User())
    asyncio.run(cmd_start(upd, ctx))
    assert get_code_status(app, code) == "authorized"
    assert any("подтвержд" in t.lower() for t in msg.replies)


def test_cmd_start_non_admin_denied():
    import asyncio

    from telegram.constants import ChatMemberStatus

    from app.bot.panel_login import cmd_start, create_login_code, get_code_status

    app = _StubApp()
    app.bot_data["settings"] = _StubSettings()
    code = create_login_code(app, "nonceY")

    class _Msg:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text):
            self.replies.append(text)

    class _Bot:
        async def get_chat_member(self, chat_id, user_id):
            return types.SimpleNamespace(status=ChatMemberStatus.MEMBER)

    msg = _Msg()
    ctx = types.SimpleNamespace(
        args=[code], application=types.SimpleNamespace(bot_data=app.bot_data), bot=_Bot()
    )
    upd = types.SimpleNamespace(
        effective_message=msg, effective_user=types.SimpleNamespace(id=999, username="x", full_name="X")
    )
    asyncio.run(cmd_start(upd, ctx))
    assert get_code_status(app, code) == "denied"


# ---------------- Настройки (.env) ----------------


def _login_and_get_csrf(port: int, path: str) -> tuple[http.client.HTTPConnection, str, str]:
    import re

    c = _conn(port)
    ck = _login(c)
    c.request("GET", path, headers={"Cookie": ck})
    r = c.getresponse()
    page = r.read().decode("utf-8")
    m = re.search(r'name="csrf" value="([^"]+)"', page)
    assert m
    return c, ck, m.group(1)


def test_config_page_renders(panel):
    _app, port = panel
    c, ck, _csrf = _login_and_get_csrf(port, "/config")
    c.request("GET", "/config", headers={"Cookie": ck})
    r = c.getresponse()
    body = r.read().decode("utf-8")
    assert r.status == 200
    assert "MIN_SCORE" in body
    assert 'value="72"' in body  # текущее значение из .env


def test_config_save_updates_env(panel):
    from urllib.parse import urlencode

    app, port = panel
    env_file = app.bot_data["_test_env_file"]
    c, ck, csrf = _login_and_get_csrf(port, "/config")
    payload = urlencode({"csrf": csrf, "action": "save", "MIN_SCORE": "90", "QUESTIONS_ONLY": "true"})
    c.request(
        "POST", "/config/save", payload,
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get
    r.read()
    text = env_file.read_text(encoding="utf-8")
    assert "MIN_SCORE=90" in text
    # токен бота не появляется и не трогается
    assert "TELEGRAM_BOT_TOKEN" not in text


def test_config_save_invalid_int_rejected(panel):
    from urllib.parse import urlencode

    app, port = panel
    env_file = app.bot_data["_test_env_file"]
    before = env_file.read_text(encoding="utf-8")
    c, ck, csrf = _login_and_get_csrf(port, "/config")
    payload = urlencode({"csrf": csrf, "action": "save", "MIN_SCORE": "abc"})
    c.request(
        "POST", "/config/save", payload,
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get: ошибка показывается flash-ем после редиректа
    r.read()
    assert env_file.read_text(encoding="utf-8") == before  # ничего не записано


def test_config_save_secret_blank_keeps_value(panel):
    from urllib.parse import urlencode

    app, port = panel
    env_file = app.bot_data["_test_env_file"]
    env_file.write_bytes(b"MIN_SCORE=72\nPANEL_PASSWORD=oldpass\n")
    c, ck, csrf = _login_and_get_csrf(port, "/config")
    # пустой пароль не должен затирать существующий
    payload = urlencode({"csrf": csrf, "action": "save", "MIN_SCORE": "72", "PANEL_PASSWORD": ""})
    c.request(
        "POST", "/config/save", payload,
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    r.read()
    assert "PANEL_PASSWORD=oldpass" in env_file.read_text(encoding="utf-8")


# ---------------- Обновление из git (кнопки в хидере) ----------------


def test_update_check_reports_available(panel, monkeypatch):
    from urllib.parse import urlencode

    _app, port = panel
    monkeypatch.setattr(
        "app.web_panel.git_ping_compare_with_remote",
        lambda **k: ("a" * 40, "b" * 40, True, None),
    )
    c, ck, csrf = _login_and_get_csrf(port, "/")
    c.request(
        "POST", "/update/check", urlencode({"csrf": csrf}),
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get
    r.read()
    c.request("GET", r.getheader("Location"), headers={"Cookie": ck})
    body = c.getresponse().read().decode("utf-8")
    assert "Есть обновление" in body


def test_update_check_up_to_date(panel, monkeypatch):
    from urllib.parse import urlencode

    _app, port = panel
    monkeypatch.setattr(
        "app.web_panel.git_ping_compare_with_remote",
        lambda **k: ("a" * 40, "a" * 40, False, None),
    )
    c, ck, csrf = _login_and_get_csrf(port, "/")
    c.request(
        "POST", "/update/check", urlencode({"csrf": csrf}),
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get
    r.read()
    c.request("GET", r.getheader("Location"), headers={"Cookie": ck})
    body = c.getresponse().read().decode("utf-8")
    assert "последняя версия" in body


def test_update_run_no_change(panel, monkeypatch):
    from urllib.parse import urlencode

    _app, port = panel
    monkeypatch.setattr(
        "app.web_panel.git_sync_from_remote", lambda **k: (False, "уже актуально")
    )
    c, ck, csrf = _login_and_get_csrf(port, "/")
    c.request(
        "POST", "/update/run", urlencode({"csrf": csrf}),
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get
    r.read()
    c.request("GET", r.getheader("Location"), headers={"Cookie": ck})
    body = c.getresponse().read().decode("utf-8")
    assert "не требуется" in body


def test_update_run_requires_csrf(panel):
    from urllib.parse import urlencode

    _app, port = panel
    c = _conn(port)
    ck = _login(c)
    c.request(
        "POST", "/update/run", urlencode({}),
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 400  # без csrf
    r.read()


def test_replies_clear_empties_feed(panel):
    from urllib.parse import urlencode

    app, port = panel
    # Заполняем ленту последних ответов и проверяем, что кнопка очистки её сбрасывает.
    app.bot_data["recent_replies"] = [
        {"ts": time.time(), "question": "Q1", "answer": "A1", "url": "", "source": "wiki", "chat_id": 1},
        {"ts": time.time(), "question": "Q2", "answer": "A2", "url": "", "source": "wiki", "chat_id": 1},
    ]
    c, ck, csrf = _login_and_get_csrf(port, "/")
    c.request(
        "POST", "/replies/clear", urlencode({"csrf": csrf}),
        {"Content-Type": "application/x-www-form-urlencoded", "Cookie": ck},
    )
    r = c.getresponse()
    assert r.status == 303  # Post-Redirect-Get
    r.read()
    assert app.bot_data["recent_replies"] == []
