from __future__ import annotations

import pytest

from app.translate_ru import Translator


def test_translation_cache_ignores_malformed_timestamp(tmp_path):
    path = tmp_path / "translations.json"
    path.write_text('{"hello world":{"ts":"broken","ru":"Привет"}}', encoding="utf-8")
    translator = Translator(cache_path=path)

    assert translator._get_cached("hello world") is None


def test_translation_cache_write_is_atomic(tmp_path):
    path = tmp_path / "translations.json"
    translator = Translator(cache_path=path)
    translator._put_cached("hello world", "Привет мир", source="test")

    assert '"Привет мир"' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".translations.json.*.tmp"))


def test_translation_cache_evicts_oldest_entries(tmp_path, monkeypatch):
    translator = Translator(cache_path=tmp_path / "translations.json", max_cache_entries=2)
    translator._loaded = True
    translator._cache = {
        "z old": {"ru": "старый", "ts": 10},
        "a newer": {"ru": "новее", "ts": 20},
    }
    monkeypatch.setattr("app.translate_ru.time.time", lambda: 30.0)

    translator._put_cached("new entry", "новая", source="test")

    assert set(translator._cache) == {"a newer", "new entry"}


def test_translation_cache_load_is_bounded(tmp_path, monkeypatch):
    path = tmp_path / "translations.json"
    path.write_text(
        "{" + ",".join(
            f'"entry {index}": {{"ru": "перевод", "ts": {index}}}'
            for index in range(5)
        ) + "}",
        encoding="utf-8",
    )
    translator = Translator(cache_path=path, max_cache_entries=2)
    monkeypatch.setattr("app.translate_ru.time.time", lambda: 5.0)

    assert translator._get_cached("entry 4") == "перевод"
    assert set(translator._cache) == {"entry 3", "entry 4"}


@pytest.mark.asyncio
async def test_translation_rejects_oversized_http_response(tmp_path, monkeypatch):
    import app.translate_ru as translate_ru

    class Response:
        content = b"x" * 100

        def raise_for_status(self) -> None:
            return None

        def json(self):
            raise AssertionError("oversized response must not be decoded")

    class Client:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(translate_ru.httpx, "AsyncClient", Client)
    monkeypatch.setattr(translate_ru, "_MAX_TRANSLATION_RESPONSE_BYTES", 10)
    translator = Translator(cache_path=tmp_path / "translations.json")

    assert await translator.translate_en_ru("a sufficiently long text") == "a sufficiently long text"
