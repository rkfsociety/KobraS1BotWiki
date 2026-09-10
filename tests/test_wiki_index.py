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
