"""Серверная проверка initData Telegram Mini App."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl


class MiniAppAuthError(ValueError):
    """Недействительные или просроченные данные Telegram Mini App."""


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86_400,
) -> dict[str, Any]:
    """Проверяет подпись Telegram Web Apps и возвращает безопасные данные сессии."""
    if not init_data or not bot_token:
        raise MiniAppAuthError("отсутствуют данные авторизации")
    if max_age_seconds <= 0:
        raise MiniAppAuthError("некорректный срок авторизации")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MiniAppAuthError("некорректный формат авторизации") from exc

    values: dict[str, str] = {}
    for key, value in pairs:
        if key in values:
            raise MiniAppAuthError("дублирующееся поле авторизации")
        values[key] = value

    received_hash = values.pop("hash", "")
    if not received_hash or len(received_hash) != 64:
        raise MiniAppAuthError("отсутствует подпись авторизации")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise MiniAppAuthError("недействительная подпись авторизации")

    try:
        auth_date = int(values.get("auth_date", ""))
    except ValueError as exc:
        raise MiniAppAuthError("некорректная дата авторизации") from exc
    if auth_date <= 0 or time.time() - auth_date > max_age_seconds:
        raise MiniAppAuthError("срок авторизации истёк")

    user_raw = values.get("user", "")
    try:
        user = json.loads(user_raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MiniAppAuthError("некорректные данные пользователя") from exc
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise MiniAppAuthError("данные пользователя отсутствуют")

    result: dict[str, Any] = dict(values)
    result["auth_date"] = auth_date
    result["user"] = user
    return result
