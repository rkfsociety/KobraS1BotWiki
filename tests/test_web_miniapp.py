"""Интеграционные тесты Telegram Mini App поверх текущего HTTP-сервера."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import sqlite3
import time
import types
from urllib.parse import urlencode

import pytest
from telegram.constants import ChatMemberStatus

from app.bot.manual_qa import load_manual_qa_store
from app.bot.missed_questions import load_missed_questions
from app.bot.chat_store import ChatStore
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
    monkeypatch.setattr("app.web_panel.project_repo_root", lambda: tmp_path)

    status_box = {
        "value": ChatMemberStatus.ADMINISTRATOR,
        "by_user": {},
        "chat_store_path": tmp_path / "data" / "chat.sqlite3",
    }

    async def get_chat_member(*, chat_id: int, user_id: int):
        assert chat_id == -100123
        return types.SimpleNamespace(status=status_box["by_user"].get(user_id, status_box["value"]))

    app = types.SimpleNamespace(
        bot=types.SimpleNamespace(get_chat_member=get_chat_member),
        bot_data={
            "settings": _Settings(),
            "wiki_index": types.SimpleNamespace(
                doc_count=42,
                search=lambda query, top_k=5: []
                if "неизвест" in query.lower()
                else [
                    (types.SimpleNamespace(title="Первый слой", url="https://wiki.example/layer", text=""), 91)
                ],
            ),
            "wiki_indexer": types.SimpleNamespace(is_done=lambda: True),
            "manual_qa_entries": [],
            "fix_store": {},
            "error_codes_catalog": {},
            "bot_stats": {"total_answers": 12},
        },
    )
    status_box["application"] = app
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
    response, payload = _create_session_response(port, user_id)
    assert response.status == 200
    return payload["session"]


def _create_session_response(port: int, user_id: int = 42) -> tuple[http.client.HTTPResponse, dict[str, object]]:
    c = _conn(port)
    body = urlencode({"init_data": _signed_init_data(user_id)})
    c.request("POST", "/api/app/session", body, {"Content-Type": "application/x-www-form-urlencoded"})
    response = c.getresponse()
    payload = json.loads(response.read())
    return response, payload


def test_miniapp_page_is_public_and_contains_telegram_sdk(mini_panel):
    c = _conn(mini_panel[0])
    c.request("GET", "/app")
    response = c.getresponse()
    body = response.read().decode()

    assert response.status == 200
    assert response.getheader("Cache-Control") == "no-store"
    assert "telegram-web-app.js" in body


def test_miniapp_shell_has_mobile_admin_dashboard_sections():
    body = render_miniapp().decode()

    assert "miniapp-shell" in body
    assert "miniapp-error" in body
    assert "Вопросы без ответа" in body
    assert "Страницы вики" in body
    assert "Ответы бота" in body
    assert "Сохранить ответ" in body
    assert "Отметить как оффтоп" in body
    assert "Поиск по вики" in body
    assert "searchWiki" in body
    assert "Режим пользователя" in body
    assert "setUserMode" in body
    assert "chat-history" in body
    assert "loadChatHistory" in body
    assert "sendChatMessage" in body
    assert "appendChatMessage" in body
    assert 'id="chat-input"' in body
    assert 'aria-label="Вопрос боту"' in body
    assert "Загрузить предыдущие сообщения" in body
    assert "askQuestion" not in body
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


def test_miniapp_group_member_gets_user_session_and_admin_dashboard_is_forbidden(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    response, payload = _create_session_response(port)

    assert response.status == 200
    assert payload["role"] == "user"
    session = payload["session"]
    c = _conn(port)
    c.request("GET", "/api/app/dashboard", headers={"Authorization": f"Bearer {session}"})
    dashboard = c.getresponse()

    assert dashboard.status == 403
    dashboard.read()


def test_miniapp_rejects_user_outside_group(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.LEFT

    response, _payload = _create_session_response(port)

    assert response.status == 403


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


def test_admin_can_search_wiki_from_miniapp(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    c = _conn(port)
    c.request("GET", "/api/app/search?" + urlencode({"q": "первый слой"}), headers={"Authorization": f"Bearer {session}"})
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["results"][0] == {
        "title": "Первый слой",
        "url": "https://wiki.example/layer",
        "score": 91,
    }


def test_empty_wiki_search_is_rejected(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    c = _conn(port)
    c.request("GET", "/api/app/search?q=", headers={"Authorization": f"Bearer {session}"})
    response = c.getresponse()

    assert response.status == 400
    assert "запрос" in json.loads(response.read())["error"].lower()


def test_admin_can_ask_question_in_user_preview_and_store_unknown_question(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    body = urlencode({"text": "неизвестный вопрос о принтере"})
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/question",
        body,
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["answered"] is False
    assert "Пока я не могу ответить" in payload["answer"]
    assert load_missed_questions()[0]["text"] == "неизвестный вопрос о принтере"


def test_admin_can_ask_question_in_user_preview_and_get_wiki_answer(mini_panel):
    port, _ = mini_panel
    session = _create_session(port)
    body = urlencode({"text": "как настроить первый слой"})
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/question",
        body,
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["answered"] is True
    assert payload["source"] == "wiki"
    assert payload["url"] == "https://wiki.example/layer"


def test_chat_history_requires_bearer_session(mini_panel):
    c = _conn(mini_panel[0])
    c.request("GET", "/api/app/chat/history")
    response = c.getresponse()

    assert response.status == 401
    assert "сессия" in json.loads(response.read())["error"].lower()


def test_chat_message_returns_manual_answer_for_group_member(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    status_box["application"].bot_data["manual_qa_entries"] = [
        {"keys": ["сопло забито"], "title": "Сопло", "answer": "Прочистите сопло."}
    ]
    session = _create_session(port, user_id=100)
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/chat/message",
        urlencode({"text": "почему сопло забито?"}),
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["role"] == "user"
    assert [message["role"] for message in payload["messages"]] == ["user", "bot"]
    assert payload["messages"][1]["source"] == "manual"
    assert payload["messages"][1]["text"] == "Прочистите сопло."


def test_chat_message_returns_wiki_answer_for_group_member(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    session = _create_session(port, user_id=101)
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/chat/message",
        urlencode({"text": "как настроить первый слой"}),
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["messages"][1]["source"] == "wiki"
    assert "Первый слой" in payload["messages"][1]["text"]


def test_chat_message_stores_missing_question_and_fallback(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    session = _create_session(port, user_id=102)
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/chat/message",
        urlencode({"text": "неизвестный вопрос о принтере"}),
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["messages"][1]["source"] == "missing"
    assert "Пока я не могу ответить" in payload["messages"][1]["text"]
    assert load_missed_questions()[0]["text"] == "неизвестный вопрос о принтере"


def test_chat_history_is_isolated_by_user_id(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    first_session = _create_session(port, user_id=201)
    second_session = _create_session(port, user_id=202)
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/chat/message",
        urlencode({"text": "как настроить первый слой"}),
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {first_session}"},
    )
    assert c.getresponse().status == 200
    c.close()
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/chat/message",
        urlencode({"text": "неизвестный вопрос о принтере"}),
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {second_session}"},
    )
    assert c.getresponse().status == 200
    c.close()
    c = _conn(port)
    c.request("GET", "/api/app/chat/history", headers={"Authorization": f"Bearer {first_session}"})
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 200
    assert payload["user"]["id"] == 201
    assert [message["user_id"] for message in payload["messages"]] == [201, 201]
    assert payload["has_more"] is False


def test_chat_message_rate_limit_rejects_new_question(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    session = _create_session(port, user_id=301)
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"}
    c = _conn(port)
    c.request("POST", "/api/app/chat/message", urlencode({"text": "как настроить первый слой"}), headers)
    first = c.getresponse()
    first.read()
    c.close()
    c = _conn(port)
    c.request("POST", "/api/app/chat/message", urlencode({"text": "другой вопрос"}), headers)
    limited = c.getresponse()
    limited_payload = json.loads(limited.read())

    assert first.status == 200
    assert limited.status == 429
    assert limited_payload["retry_after"] >= 1


def test_chat_message_duplicate_reuses_pair_without_search_or_extra_rate_event(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    search_calls = {"count": 0}

    def search(query: str, top_k: int = 1):
        search_calls["count"] += 1
        return [(types.SimpleNamespace(title="Первый слой", url="https://wiki.example/layer", text=""), 91)]

    status_box["application"].bot_data["wiki_index"] = types.SimpleNamespace(doc_count=42, search=search)
    session = _create_session(port, user_id=350)
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"}
    c = _conn(port)
    c.request("POST", "/api/app/chat/message", urlencode({"text": "как настроить первый слой"}), headers)
    first = c.getresponse()
    first_payload = json.loads(first.read())
    c.close()
    c = _conn(port)
    c.request("POST", "/api/app/chat/message", urlencode({"text": "как настроить первый слой"}), headers)
    duplicate = c.getresponse()
    duplicate_payload = json.loads(duplicate.read())

    with sqlite3.connect(status_box["chat_store_path"]) as connection:
        rate_events = connection.execute(
            "SELECT COUNT(*) FROM rate_limit_events WHERE user_id = ?", (350,)
        ).fetchone()[0]

    assert first.status == 200
    assert duplicate.status == 200
    assert [message["id"] for message in duplicate_payload["messages"]] == [
        message["id"] for message in first_payload["messages"]
    ]
    assert search_calls["count"] == 1
    assert rate_events == 1


def test_chat_message_search_error_is_stored_with_error_source(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER

    def search(_query: str, top_k: int = 1):
        raise RuntimeError("wiki unavailable")

    status_box["application"].bot_data["wiki_index"] = types.SimpleNamespace(doc_count=42, search=search)
    session = _create_session(port, user_id=360)
    c = _conn(port)
    c.request(
        "POST",
        "/api/app/chat/message",
        urlencode({"text": "как настроить первый слой"}),
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Bearer {session}"},
    )
    response = c.getresponse()
    payload = json.loads(response.read())

    assert response.status == 503
    assert payload["messages"][1]["source"] == "error"
    assert payload["messages"][1]["reply_to_id"] == payload["messages"][0]["id"]


def test_chat_history_caps_page_at_fifty_and_uses_before_id(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    session = _create_session(port, user_id=370)
    store = ChatStore(status_box["chat_store_path"])
    try:
        messages = [store.add_message(370, "user", f"question {index}", "miniapp") for index in range(55)]
    finally:
        store.close()

    c = _conn(port)
    c.request("GET", "/api/app/chat/history?limit=200", headers={"Authorization": f"Bearer {session}"})
    first_response = c.getresponse()
    first_page = json.loads(first_response.read())
    c.close()
    oldest_id = first_page["messages"][0]["id"]
    c = _conn(port)
    c.request(
        "GET",
        f"/api/app/chat/history?before_id={oldest_id}",
        headers={"Authorization": f"Bearer {session}"},
    )
    second_response = c.getresponse()
    second_page = json.loads(second_response.read())

    assert first_response.status == 200
    assert len(first_page["messages"]) == 50
    assert first_page["messages"][0]["id"] == messages[5].id
    assert first_page["messages"][-1]["id"] == messages[-1].id
    assert first_page["has_more"] is True
    assert second_response.status == 200
    assert [message["id"] for message in second_page["messages"]] == [message.id for message in messages[:5]]
    assert second_page["has_more"] is False


def test_user_session_is_forbidden_from_missed_mutations(mini_panel):
    port, status_box = mini_panel
    status_box["value"] = ChatMemberStatus.MEMBER
    session = _create_session(port, user_id=380)
    headers = {"Authorization": f"Bearer {session}"}
    requests = [
        ("GET", "/api/app/missed", None),
        ("POST", "/api/app/missed/not-used/answer", urlencode({"title": "x", "answer": "x"})),
        ("POST", "/api/app/missed/not-used/dismiss", None),
    ]

    for method, path, body in requests:
        c = _conn(port)
        request_headers = dict(headers)
        if body is not None:
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body, request_headers)
        response = c.getresponse()

        assert response.status == 403
        response.read()
