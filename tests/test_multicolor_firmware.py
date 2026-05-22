"""Прошивка и многоцветная печать: без уточнения модели, не resin M3."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _needs_model_clarification,
    _topic_is_multicolor_firmware_intent,
    _topic_needs_printer_model,
)
from app.bot.wiki_ranking import (
    _multicolor_firmware_guide_url_plausible,
    _response_wiki_url_acceptable,
    _search_best_with_model_bias,
    _topic_path_bonus,
)
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiDoc

_MSG = "Это же не та прошивка, где цветная печать косячит? Или та же?"

_S1_FW = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-s1-combo/firmware-update-guide"
_K3_LOG = "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/firmware-upgrade-log"
_SLICER = "https://wiki.anycubic.com/en/software-and-app/anycubicslicer/multi-color-printing"
_RESIN = "https://wiki.anycubic.com/en/resin-3d-printer/m3-premium/firmware-update"
_BAD = "https://wiki.anycubic.com/en/fdm-3d-printer/vyper/vyper-replace-the-nozzle"


class _FakeIndex:
    def __init__(self, docs: list[WebWikiDoc]) -> None:
        self._docs = docs

    def search(self, q: str, top_k: int = 28):
        from rapidfuzz import fuzz

        from app.web_wiki_index import _make_search_blob, _normalize

        qn = _normalize(q)
        scored = [(d, fuzz.token_set_ratio(qn, _make_search_blob(d))) for d in self._docs]
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


def test_multicolor_firmware_intent_detected():
    assert _topic_is_multicolor_firmware_intent(_MSG)


def test_multicolor_firmware_no_model_clarify():
    assert not _topic_needs_printer_model(_MSG)
    assert not _needs_model_clarification(_MSG)


def test_multicolor_firmware_url_plausible():
    for url in (_S1_FW, _K3_LOG, _SLICER):
        assert _multicolor_firmware_guide_url_plausible(url)
        assert _response_wiki_url_acceptable(_MSG, url)
    assert not _multicolor_firmware_guide_url_plausible(_RESIN)
    assert not _response_wiki_url_acceptable(_MSG, _RESIN)
    assert not _response_wiki_url_acceptable(_MSG, _BAD)


def test_resin_firmware_penalized_in_ranking():
    assert _topic_path_bonus(_MSG, _RESIN) < 0
    assert _topic_path_bonus(_MSG, _S1_FW) > _topic_path_bonus(_MSG, _RESIN)


def test_search_prefers_s1_firmware_over_resin():
    docs = _docs_from_urls((_S1_FW, _K3_LOG, _SLICER, _RESIN, _BAD))
    variants = expand_queries(_MSG)
    doc, score = _search_best_with_model_bias(
        _FakeIndex(docs), variants, context_text=_MSG, topic_for_keywords=_MSG
    )
    assert doc is not None
    assert "kobra-s1-combo" in doc.url or "kobra-3-combo" in doc.url
    assert "resin-3d-printer" not in doc.url
    assert score >= 55
