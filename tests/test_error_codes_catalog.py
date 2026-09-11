from __future__ import annotations

import pytest

import app.error_codes_catalog as catalog


class _Response:
    text = "<table><tr><td>11527</td><td>Test error</td></tr></table>"

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        return None

    async def get(self, url: str) -> _Response:
        return _Response()


@pytest.mark.asyncio
async def test_invalid_cache_metadata_does_not_abort_refresh(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text('{"ts":"broken","count":"broken","parser_version":"broken"}', encoding="utf-8")
    monkeypatch.setattr(catalog.httpx, "AsyncClient", _Client)

    result = await catalog.ensure_error_codes_catalog(
        base_url="https://wiki.anycubic.com",
        cache_path=path,
        refresh_hours=24,
    )

    assert result["11527"].title == "Test error"


@pytest.mark.asyncio
async def test_corrupted_cached_entry_does_not_hide_valid_entries(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text(
        '{"ts": 1000, "count": 2, "parser_version": 2, "codes": {'
        '"11527": {"code": "11527", "title": "Valid"}, '
        '"broken": {"title": 7}, '
        '"11528": {"code": "11528", "cause": "Cause"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "_now", lambda: 1001.0)

    result = await catalog.ensure_error_codes_catalog(
        base_url="https://wiki.anycubic.com",
        cache_path=path,
        refresh_hours=24,
    )

    assert set(result) == {"11527", "11528"}
    assert result["11527"].title == "Valid"


def test_cache_loader_rejects_oversized_file_before_json_decode(tmp_path, monkeypatch):
    path = tmp_path / "catalog.json"
    path.write_text("{}" * 20, encoding="utf-8")
    monkeypatch.setattr(catalog, "_MAX_CACHE_BYTES", 10)

    assert catalog._load_json(path) is None


@pytest.mark.asyncio
async def test_error_codes_rejects_oversized_http_response(tmp_path, monkeypatch):
    class Response:
        text = "x" * 100

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str) -> Response:
            return Response()

    monkeypatch.setattr(catalog.httpx, "AsyncClient", Client)
    monkeypatch.setattr(catalog, "_MAX_RESPONSE_BYTES", 10)

    result = await catalog.ensure_error_codes_catalog(
        base_url="https://wiki.anycubic.com",
        cache_path=tmp_path / "catalog.json",
    )

    assert result == {}
