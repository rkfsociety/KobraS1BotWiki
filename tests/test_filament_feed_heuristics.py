"""Подача филамента / срывы шестерни на Kobra S1."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _model_slug_hints,
    _needs_model_clarification,
    _topic_is_filament_feed_intent,
)
from app.bot.wiki_ranking import (
    _filament_feed_guide_url_plausible,
    _response_wiki_url_acceptable,
    _search_best_with_model_bias,
    _topic_path_bonus,
    _wrong_part_for_topic_penalty,
)
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiDoc

_FILAMENT_MSG = (
    "Привет всем. Может кто подскажет, как проверить мотор на подачу филамента, "
    "и и драйвер к нему . кобра S1  Перестал подавать филамент. Разобрал - мотор крутит. "
    "Собираю - не подает. Пальцами зажимаю шестерню- в какие-то моменты срывы в обе стороны. "
    "подключил другой мотор(больше не много размером) тоже то срывы есть."
)

_GOOD = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/troubleshooting-abnormal-print-head-clogging",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/11511-feeding-timeout",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/11518-abnormal-blocking",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/extruder-module-replacement-guide",
)

_BAD = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/z-axis-motor",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-2/extruder-motor-replacement-guide",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/assembly",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1/printer-binding-guide",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-max/extruder-replacement",
)

_SHORT_GEARS = "Шестерни не тянут?"


class _FakeIndex:
    def __init__(self, docs: list[WebWikiDoc]) -> None:
        self._docs = docs

    def search(self, q: str, top_k: int = 28):
        from rapidfuzz import fuzz

        from app.web_wiki_index import _make_search_blob, _normalize

        qn = _normalize(q)
        scored = [
            (d, fuzz.token_set_ratio(qn, _make_search_blob(d)))
            for d in self._docs
        ]
        scored = [(d, s) for d, s in scored if s > 25]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


def _docs_from_urls(urls: tuple[str, ...]) -> list[WebWikiDoc]:
    out: list[WebWikiDoc] = []
    for u in urls:
        slug = u.split("/en/")[-1]
        title = slug.replace("-", " ").replace("/", " ")
        out.append(WebWikiDoc(url=u, title=title, text=title + " " + slug))
    return out


def test_filament_feed_intent_detected():
    assert _topic_is_filament_feed_intent(_FILAMENT_MSG)


def test_short_gears_question_needs_model_and_rejects_max_replacement():
    assert _topic_is_filament_feed_intent(_SHORT_GEARS)
    assert _needs_model_clarification(_SHORT_GEARS)
    assert not _response_wiki_url_acceptable(_SHORT_GEARS, _BAD[-1])


def test_cyrillic_kobra_s1_hints():
    hints = _model_slug_hints(_FILAMENT_MSG)
    assert "kobra-s1" in hints
    assert "kobra-s1-combo" in hints


def test_expand_queries_filament_troubleshooting():
    variants = expand_queries(_FILAMENT_MSG)
    assert any("clogging" in v and "feeding" in v for v in variants)


def test_good_urls_plausible_and_acceptable():
    for url in _GOOD:
        assert _filament_feed_guide_url_plausible(url)
        assert _response_wiki_url_acceptable(_FILAMENT_MSG, url)


def test_bad_urls_rejected():
    for url in _BAD:
        assert not _response_wiki_url_acceptable(_FILAMENT_MSG, url)


def test_clogging_beats_z_motor_and_kobra2():
    clog = _GOOD[0]
    z_motor = _BAD[0]
    k2 = _BAD[1]
    assert _topic_path_bonus(_FILAMENT_MSG, clog) > _topic_path_bonus(_FILAMENT_MSG, z_motor)
    assert _wrong_part_for_topic_penalty(_FILAMENT_MSG, z_motor) >= 78
    assert _wrong_part_for_topic_penalty(_FILAMENT_MSG, k2) == 0  # штраф через model penalty


def test_search_picks_clogging_for_filament_msg():
    docs = _docs_from_urls(_GOOD + _BAD)
    idx = _FakeIndex(docs)
    variants = expand_queries(_FILAMENT_MSG)
    doc, score = _search_best_with_model_bias(
        idx, variants, context_text=_FILAMENT_MSG, topic_for_keywords=_FILAMENT_MSG
    )
    assert doc is not None
    assert score >= 72
    assert "clogging" in doc.url or "feeding-timeout" in doc.url or "abnormal-blocking" in doc.url
    assert _response_wiki_url_acceptable(_FILAMENT_MSG, doc.url)
