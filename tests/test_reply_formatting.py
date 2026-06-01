"""Красивые карточки ответов бота (единый формат со ссылкой на вики)."""
from __future__ import annotations

from app.bot.error_display import _format_error_code_info
from app.bot.i18n import format_wiki_card
from app.error_codes_catalog import ErrorCodeInfo

_URL = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"


def test_wiki_card_has_emoji_header_and_clickable_title():
    card = format_wiki_card(
        lang="ru", header_key="already_in_wiki",
        title="Firmware update guide", url=_URL, score=100,
    )
    assert "📚" in card
    # заголовок без хвостового двоеточия
    assert "вики</b>" in card
    # заголовок статьи — кликабельная ссылка, а не голый url
    assert f'<a href="{_URL}">Firmware update guide</a>' in card
    assert "🎯 совпадение: 100%" in card


def test_wiki_card_escapes_title():
    card = format_wiki_card(
        lang="ru", header_key="found_in_wiki",
        title="A & B <C>", url=_URL, score=80,
    )
    assert "A &amp; B &lt;C&gt;" in card
    assert "<C>" not in card


def test_wiki_card_falls_back_to_url_when_no_title():
    card = format_wiki_card(
        lang="ru", header_key="found_in_wiki", title="", url=_URL, score=72,
    )
    assert _URL in card


def test_wiki_card_en():
    card = format_wiki_card(
        lang="en", header_key="already_in_wiki",
        title="Firmware update guide", url=_URL, score=90,
    )
    assert "📚" in card
    assert "match: 90%" in card


def test_error_code_card_has_structure_emojis():
    card = _format_error_code_info(
        ErrorCodeInfo(code="8000", title="ACE busy", cause="busy", fix="wait"),
        lang="en",
    )
    assert "🔧 <b>Error 8000</b>" in card
    assert "⚠️" in card
    assert "✅" in card
