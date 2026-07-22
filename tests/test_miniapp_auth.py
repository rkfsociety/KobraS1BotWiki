"""Проверка серверной валидации Telegram Mini App initData."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.bot.miniapp_auth import MiniAppAuthError, validate_init_data


BOT_TOKEN = "123456:TESTTOKEN"


def _signed_init_data(*, auth_date: int | None = None, user: dict | None = None) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAH123",
        "user": json.dumps(
            user or {"id": 42, "first_name": "Admin", "username": "admin"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_validate_init_data_returns_verified_user_and_auth_date():
    result = validate_init_data(_signed_init_data(), BOT_TOKEN)

    assert result["auth_date"] <= int(time.time())
    assert result["user"] == {"id": 42, "first_name": "Admin", "username": "admin"}


def test_validate_init_data_rejects_changed_field():
    raw = _signed_init_data().replace("query_id=AAH123", "query_id=changed")

    with pytest.raises(MiniAppAuthError):
        validate_init_data(raw, BOT_TOKEN)


def test_validate_init_data_rejects_wrong_hash():
    raw = _signed_init_data().replace("hash=", "hash=0", 1)

    with pytest.raises(MiniAppAuthError):
        validate_init_data(raw, BOT_TOKEN)


def test_validate_init_data_rejects_expired_auth_date():
    raw = _signed_init_data(auth_date=int(time.time()) - 86_401)

    with pytest.raises(MiniAppAuthError):
        validate_init_data(raw, BOT_TOKEN, max_age_seconds=86_400)


def test_validate_init_data_rejects_missing_user():
    raw = _signed_init_data()
    fields = [part for part in raw.split("&") if not part.startswith("user=")]
    unsigned = "&".join(fields)

    with pytest.raises(MiniAppAuthError):
        validate_init_data(unsigned, BOT_TOKEN)


def test_validate_init_data_rejects_duplicate_critical_field():
    raw = _signed_init_data() + "&auth_date=123"

    with pytest.raises(MiniAppAuthError):
        validate_init_data(raw, BOT_TOKEN)
