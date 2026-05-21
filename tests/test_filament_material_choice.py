"""Выбор TPU/пластика: без уточнения модели, без ссылки на замену сопла."""
from __future__ import annotations

from app.bot.text_heuristics import (
    _needs_model_clarification,
    _topic_is_filament_material_choice_intent,
    _topic_needs_printer_model,
)
from app.bot.wiki_ranking import (
    _filament_material_guide_url_plausible,
    _response_wiki_url_acceptable,
    _search_best_with_model_bias,
)
from app.ru_layer import expand_queries
from app.web_wiki_index import WebWikiDoc

_TPU_MSG = (
    "Друзья подскажите на родное сопло какой ТПУ пластик взять и какой фирмы?"
)

_GOOD = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/print-tpu",
    "https://wiki.anycubic.com/en/filament-and-resin/filament-guide",
    "https://wiki.anycubic.com/en/filament-and-resin/parameters-selection",
)

_BAD = (
    "https://wiki.anycubic.com/en/fdm-3d-printer/vyper/vyper-replace-the-nozzle",
    "https://wiki.anycubic.com/en/fdm-3d-printer/kobra-2/repalce-nozzle",
)


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


def test_tpu_material_intent_detected():
    assert _topic_is_filament_material_choice_intent(_TPU_MSG)


def test_tpu_question_does_not_need_model_clarify():
    assert not _topic_needs_printer_model(_TPU_MSG)
    assert not _needs_model_clarification(_TPU_MSG)


def test_material_urls_plausible():
    for url in _GOOD:
        assert _filament_material_guide_url_plausible(url)
        assert _response_wiki_url_acceptable(_TPU_MSG, url)


def test_nozzle_replace_urls_rejected_for_tpu():
    for url in _BAD:
        assert not _filament_material_guide_url_plausible(url)
        assert not _response_wiki_url_acceptable(_TPU_MSG, url)


def test_search_prefers_print_tpu_over_nozzle_replace():
    docs = _docs_from_urls(_GOOD + _BAD)
    idx = _FakeIndex(docs)
    variants = expand_queries(_TPU_MSG)
    doc, score = _search_best_with_model_bias(
        idx, variants, context_text=_TPU_MSG, topic_for_keywords=_TPU_MSG
    )
    assert doc is not None
    assert score >= 60
    assert "print-tpu" in doc.url or "filament-guide" in doc.url
    assert _response_wiki_url_acceptable(_TPU_MSG, doc.url)
