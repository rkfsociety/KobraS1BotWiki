from __future__ import annotations

from app.wiki_index import WikiDoc, WikiIndex


def test_search_top_k_keeps_document_order_for_equal_scores():
    index = WikiIndex([
        WikiDoc(title="same", slug="first", text="same"),
        WikiDoc(title="same", slug="second", text="same"),
    ])

    assert [doc.slug for doc, _ in index.search("same", top_k=2)] == ["first", "second"]


def test_search_empty_query_returns_no_arbitrary_document():
    index = WikiIndex([WikiDoc(title="article", slug="article", text="article")])

    assert index.search("   ") == []


def test_search_reuses_bounded_cache_without_exposing_cached_list(monkeypatch):
    index = WikiIndex([
        WikiDoc(title="one", slug="one", text="printer bed"),
        WikiDoc(title="two", slug="two", text="printer nozzle"),
    ])
    calls = 0
    original = __import__("app.wiki_index", fromlist=["fuzz"]).fuzz.token_set_ratio

    def counted_ratio(query, text):
        nonlocal calls
        calls += 1
        return original(query, text)

    monkeypatch.setattr("app.wiki_index.fuzz.token_set_ratio", counted_ratio)
    first = index.search("printer", top_k=2)
    first.clear()
    second = index.search("printer", top_k=2)

    assert calls == 2
    assert [doc.slug for doc, _ in second] == ["one", "two"]
