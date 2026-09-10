from __future__ import annotations

import threading

from app.web_wiki_index import (
    WebWikiIndex,
    WebWikiDoc,
    _extract_text_from_html,
    _read_sitemap_urls,
)


def test_extracts_wikijs_template_contents_instead_of_app_shell():
    title, text = _extract_text_from_html(
        """
        <html><head><title>Test page | Anycubic Wiki</title></head>
        <body><div id="root"><template slot="contents">
          <h1>Real article</h1><p>Replace the hotend carefully.</p>
        </template><nav>Navigation only</nav></div></body></html>
        """
    )

    assert title == "Test page | Anycubic Wiki"
    assert "real article" in text
    assert "replace the hotend carefully" in text
    assert "navigation only" not in text


def test_replace_docs_rebuilds_search_blobs():
    index = WebWikiIndex([WebWikiDoc(title="old", url="https://wiki.test/old", text="old")])
    index.replace_docs([WebWikiDoc(title="new", url="https://wiki.test/new", text="new")])

    assert index.doc_count == 1
    assert index.search("new")[0][0].url == "https://wiki.test/new"


def test_search_top_k_keeps_document_order_for_equal_scores():
    index = WebWikiIndex([
        WebWikiDoc(title="same", url="https://wiki.test/first", text="same"),
        WebWikiDoc(title="same", url="https://wiki.test/second", text="same"),
    ])

    assert [doc.url for doc, _ in index.search("same", top_k=2)] == [
        "https://wiki.test/first",
        "https://wiki.test/second",
    ]


def test_search_empty_query_returns_no_arbitrary_document():
    index = WebWikiIndex([
        WebWikiDoc(title="article", url="https://wiki.test/article", text="article"),
    ])

    assert index.search("   ") == []


def test_search_does_not_cache_snapshot_completed_before_index_update(monkeypatch):
    index = WebWikiIndex([
        WebWikiDoc(title="same", url="https://wiki.test/old", text="same"),
    ])
    scoring_started = threading.Event()
    release_scoring = threading.Event()
    original_score_one = index._score_one

    def slow_score_one(*args):
        scoring_started.set()
        assert release_scoring.wait(timeout=2)
        return original_score_one(*args)

    monkeypatch.setattr(index, "_score_one", slow_score_one)
    worker = threading.Thread(target=index.search, args=("same",))
    worker.start()
    assert scoring_started.wait(timeout=2)

    index.replace_docs([
        WebWikiDoc(title="same", url="https://wiki.test/new", text="same"),
    ])
    release_scoring.set()
    worker.join(timeout=2)
    assert not worker.is_alive()

    assert index.search("same")[0][0].url == "https://wiki.test/new"


def test_sitemap_urls_are_deduplicated_and_extra_urls_are_added(monkeypatch):
    class Response:
        text = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://wiki.test/en/a</loc></url>
          <url><loc>https://wiki.test/en/a</loc></url>
          <url><loc>https://outside.test/en/no</loc></url>
        </urlset>
        """

        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            pass

        def get(self, url):
            return Response()

    monkeypatch.setattr("app.web_wiki_index.httpx.Client", Client)

    urls = _read_sitemap_urls(
        "https://wiki.test/sitemap.xml",
        max_pages=10,
        base_url="https://wiki.test",
        extra_urls=("https://wiki.test/en/extra", "https://wiki.test/en/a"),
    )

    assert urls == ["https://wiki.test/en/a", "https://wiki.test/en/extra"]
