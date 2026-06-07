"""Смоук-тесты встроенной веб-панели: вход, защита, страницы, CRUD ручных ответов."""
from __future__ import annotations

import http.client
import time
import types

import pytest

from app.web_panel import start_web_panel


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
    app = _StubApp()
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
    assert r.status == 200
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
