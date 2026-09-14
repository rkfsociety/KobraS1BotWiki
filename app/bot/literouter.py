"""Минимальный OpenAI-compatible клиент для LiteRouter."""
from __future__ import annotations

import logging
from typing import Any

import httpx


class LiteRouterError(RuntimeError):
    """Ошибка запроса к LiteRouter без раскрытия API-ключа."""


def _error_detail(response: httpx.Response, *, secret: str = "") -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                detail = message.strip()
                if secret:
                    detail = detail.replace(secret, "***")
                return " ".join(detail.split())[:240]
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            detail = message.strip()
            if secret:
                detail = detail.replace(secret, "***")
            return " ".join(detail.split())[:240]

    detail = response.text.strip() or "пустой ответ провайдера"
    if secret:
        detail = detail.replace(secret, "***")
    return " ".join(detail.split())[:240]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts).strip()
    return ""


async def ask_literouter(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout_seconds: int,
    max_tokens: int | None,
) -> str:
    """Отправляет один non-streaming chat completion в LiteRouter."""
    key = (api_key or "").strip()
    if not key:
        raise LiteRouterError("не задан LITEROUTER_API_KEY")

    model_name = (model or "").strip()
    if not model_name:
        raise LiteRouterError("не задан LITEROUTER_MODEL")

    endpoint = f"{(base_url or '').strip().rstrip('/')}/chat/completions"
    if not endpoint.startswith("https://"):
        raise LiteRouterError("LITEROUTER_BASE_URL должен начинаться с https://")

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }
    if max_tokens is not None and int(max_tokens) > 0:
        payload["max_tokens"] = max(64, int(max_tokens))
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=max(1, int(timeout_seconds)), follow_redirects=False) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
    except httpx.HTTPError as exc:
        raise LiteRouterError(f"сетевой сбой: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        detail = _error_detail(response, secret=key)
        logging.warning("LiteRouter вернул HTTP %s: %s", response.status_code, detail)
        raise LiteRouterError(f"провайдер вернул HTTP {response.status_code}: {detail}")

    try:
        data = response.json()
    except ValueError as exc:
        raise LiteRouterError("провайдер вернул некорректный JSON") from exc

    try:
        choices = data["choices"]
        choice = choices[0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LiteRouterError("в ответе провайдера нет текста модели") from exc

    if choice.get("finish_reason") == "length":
        raise LiteRouterError("модель достигла лимита токенов")

    answer = _content_to_text(content)
    if not answer:
        raise LiteRouterError("модель вернула пустой ответ")
    return answer
