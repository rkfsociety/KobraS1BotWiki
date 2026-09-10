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
