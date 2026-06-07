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


def test_disabled_when_no_password():
    class Off(_StubSettings):
        panel_password = ""

    assert start_web_panel(_StubApp(), Off()) is None


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
