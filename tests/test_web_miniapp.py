"""Интеграционные тесты Telegram Mini App поверх текущего HTTP-сервера."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import time
import types
from urllib.parse import urlencode

import pytest
from telegram.constants import ChatMemberStatus

from app.bot.manual_qa import load_manual_qa_store
from app.web_miniapp import render_miniapp
from app.web_panel import start_web_panel


BOT_TOKEN = "123456:TESTTOKEN"


def _signed_init_data(user_id: int = 42) -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAH123",
        "user": json.dumps({"id": user_id, "first_name": "Admin"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class _Settings:
    panel_enabled = True
    panel_password = "secret"
    panel_username = "admin"
    panel_host = "127.0.0.1"
    panel_port = 0
    panel_session_ttl_seconds = 3600
    panel_admin_chat_id = -100123
    telegram_bot_token = BOT_TOKEN


@pytest.fixture()
def mini_panel(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("MIN_SCORE=72\n", encoding="utf-8")
    monkeypatch.setattr("app.web_panel._env_file_path", lambda: env_file)
    missed_file = tmp_path / "missed_questions.json"
    missed_file.write_text(
        json.dumps([{"text": "как настроить первый слой", "score": 12, "count": 1, "ts": 1}]),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.bot.missed_questions._path", lambda: missed_file)
    monkeypatch.setattr("app.bot.manual_qa._manual_qa_path", lambda: tmp_path / "manual_qa.json")

    status_box = {"value": ChatMemberStatus.ADMINISTRATOR}

    async def get_chat_member(*, chat_id: int, user_id: int):
        assert chat_id == -100123
        return types.SimpleNamespace(status=status_box["value"])

    app = types.SimpleNamespace(
        bot=types.SimpleNamespace(get_chat_member=get_chat_member),
        bot_data={
            "settings": _Settings(),
            "wiki_index": types.SimpleNamespace(doc_count=42),
            "wiki_indexer": types.SimpleNamespace(is_done=lambda: True),
            "manual_qa_entries": [],
            "fix_store": {},
            "error_codes_catalog": {},
            "bot_stats": {"total_answers": 12},
        },
    )
    server = start_web_panel(app, _Settings())
    assert server is not None
    time.sleep(0.05)
    try:
        yield server.server_address[1], status_box
    finally:
        server.shutdown()


def _conn(port: int) -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", port, timeout=5)


def _create_session(port: int, user_id: int = 42) -> str:
    c = _conn(port)
    body = urlencode({"init_data": _signed_init_data(user_id)})
    c.request("POST", "/api/app/session", body, {"Content-Type": "application/x-www-form-urlencoded"})
    response = c.getresponse()
    payload = json.loads(response.read())
    assert response.status == 200
    return payload["session"]


def test_miniapp_page_is_public_and_contains_telegram_sdk(mini_panel):
    c = _conn(mini_panel[0])
    c.request("GET", "/app")
    response = c.getresponse()
    body = response.read().decode()

    assert response.status == 200
    assert "telegram-web-app.js" in body


def test_miniapp_shell_has_mobile_admin_dashboard_sections():
    body = render_miniapp().decode()

    assert "miniapp-shell" in body
    assert "Вопросы без ответа" in body
    assert "Страницы вики" in body
    assert "Ответы бота" in body
    assert "Сохранить ответ" in body
    assert "Отметить как оффтоп" in body
    assert "miniapp-card" in body
    assert "env_safe" not in body


def test_admin_session_and_dashboard_are_available(mini_panel):
    session = _create_session(mini_panel[0])
    c = _conn(mini_panel[0])
    c.request("GET", "/api/app/dashboard", headers={"Authorization": f"Bearer {session}"})
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["role"] == "admin"
    assert payload["user"]["id"] == 42
    assert payload["stats"]["wiki_pages"] == 42


def test_miniapp_dashboard_rejects_missing_session(mini_panel):
    c = _conn(mini_panel[0])
    c.request("GET", "/api/app/dashboard")
    response = c.getresponse()

    assert response.status == 401
    response.read()


def test_miniapp_rejects_non_admin(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    c = _conn(port)
    body = urlencode({"init_data": _signed_init_data()})
    c.request("POST", "/api/app/session", body, {"Content-Type": "application/x-www-form-urlencoded"})
    response = c.getresponse()

    assert response.status == 403
    response.read()


def test_admin_can_answer_missed_question_from_miniapp(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    c = _conn(port)
    c.request("GET", "/api/app/missed", headers={"Authorization": f"Bearer {session}"})
    listed = c.getresponse()
    item = json.loads(listed.read())["items"][0]

    body = urlencode({"title": "Первый слой", "answer": "Проверьте стол и запустите калибровку."})
    c.request(
        "POST",
        f"/api/app/missed/{item['id']}/answer",
        body,
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    assert response.status == 200
    assert json.loads(response.read())["ok"] is True
    assert load_manual_qa_store()[0]["answer"] == "Проверьте стол и запустите калибровку."


def test_admin_can_dismiss_missed_question_from_miniapp(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    c = _conn(port)
    c.request("GET", "/api/app/missed", headers={"Authorization": f"Bearer {session}"})
    item = json.loads(c.getresponse().read())["items"][0]
    c.request("POST", f"/api/app/missed/{item['id']}/dismiss", headers={"Authorization": f"Bearer {session}"})
    response = c.getresponse()

    assert response.status == 200
    assert json.loads(response.read())["ok"] is True


def test_empty_manual_answer_does_not_remove_question(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    c = _conn(port)
    c.request("GET", "/api/app/missed", headers={"Authorization": f"Bearer {session}"})
    item = json.loads(c.getresponse().read())["items"][0]
    body = urlencode({"answer": "   "})
    c.request(
        "POST",
        f"/api/app/missed/{item['id']}/answer",
        body,
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()

    assert response.status == 400
    assert json.loads(response.read())["ok"] is False
