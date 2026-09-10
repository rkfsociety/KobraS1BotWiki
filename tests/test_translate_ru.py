from __future__ import annotations

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
