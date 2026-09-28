"""Красивые карточки ответов бота (единый формат со ссылкой на вики)."""
from __future__ import annotations

from app.bot.error_display import _format_error_code_info
from app.bot.i18n import format_wiki_card
from app.error_codes_catalog import ErrorCodeInfo


def test_error_catalog_cache_write_is_atomic(tmp_path):
    from app.error_codes_catalog import _save_json

    path = tmp_path / "catalog.json"
    _save_json(path, {"count": 1, "codes": {}})

    assert '"count": 1' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".catalog.json.*.tmp"))

_URL = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"


def test_wiki_card_is_russian_and_does_not_expose_english_source_title():
    card = format_wiki_card(
        lang="ru", header_key="already_in_wiki",
        title="Firmware update guide", url=_URL, score=100,
    )
    assert "📚" in card
    # заголовок без хвостового двоеточия
    assert "вики</b>" in card
    assert f'<a href="{_URL}">Открыть статью в вики</a>' in card
    assert "Firmware update guide" not in card
    assert "🎯 совпадение: 100%" in card


def test_wiki_card_does_not_render_untrusted_source_title():
    card = format_wiki_card(
        lang="ru", header_key="found_in_wiki",
        title="A & B <C>", url=_URL, score=80,
    )
    assert "A & B <C>" not in card
    assert "Открыть статью в вики" in card


def test_wiki_card_has_russian_label_when_source_title_is_missing():
    card = format_wiki_card(
        lang="ru", header_key="found_in_wiki", title="", url=_URL, score=72,
    )
    assert f'<a href="{_URL}">Открыть статью в вики</a>' in card


def test_wiki_card_en():
    card = format_wiki_card(
        lang="en", header_key="already_in_wiki",
        title="Firmware update guide", url=_URL, score=90,
    )
    assert "📚" in card
    assert "совпадение: 90%" in card
    assert "Firmware update guide" not in card


def test_error_code_card_has_structure_emojis():
    card = _format_error_code_info(
        ErrorCodeInfo(code="8000", title="ACE busy", cause="busy", fix="wait"),
        lang="en",
    )
    assert "🔧 <b>Error 8000</b>" in card
    assert "⚠️" in card
    assert "✅" in card
