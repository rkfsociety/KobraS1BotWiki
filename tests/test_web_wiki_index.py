from __future__ import annotations

import threading

import pytest

from app.web_wiki_index import (
    WebWikiIndex,
    WebWikiDoc,
    WebWikiIndexer,
    _extract_text_from_html,
    _fetch_docs,
    _read_sitemap_urls,
    _save_cache,
)


def test_indexer_normalizes_corrupted_state_without_refetching_valid_urls(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "cache.json"
    state_path.write_text(
        '{"cache_version": "2", "sitemap_url": 7, "base_url": null, '
        '"max_pages": -1, "urls": [" https://wiki.test/a ", 3], '
        '"next_idx": -4, "done_notified": "false"}',
        encoding="utf-8",
    )

    def fail_refetch(*_args, **_kwargs):
        raise AssertionError("valid cached URLs must not trigger sitemap fetch")

    monkeypatch.setattr("app.web_wiki_index._read_sitemap_urls", fail_refetch)
    indexer = WebWikiIndexer(
        index=WebWikiIndex.empty(),
        cache_path=str(cache_path),
        state_path=str(state_path),
        sitemap_url="https://wiki.test/sitemap.xml",
        base_url="https://wiki.test",
        max_pages=100,
    )

    assert indexer._state.urls == ["https://wiki.test/a"]
    assert indexer._state.next_idx == 0
    assert indexer._state.max_pages == 100
    assert indexer._state.done_notified is False


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


def test_search_cache_hit_returns_copy():
    index = WebWikiIndex([
        WebWikiDoc(title="one", url="https://example.test/one", text="printer bed"),
        WebWikiDoc(title="two", url="https://example.test/two", text="printer nozzle"),
    ])

    first = index.search("printer", top_k=2)
    first.clear()

    assert [doc.title for doc, _ in index.search("printer", top_k=2)] == ["one", "two"]


def test_search_normalizes_equivalent_top_k_cache_keys():
    index = WebWikiIndex([
        WebWikiDoc(title="one", url="https://example.test/one", text="printer bed"),
    ])

    index.search("printer", top_k=0)
    index.search("printer", top_k=-1)

    assert len(index._search_cache) == 1


def test_index_cache_save_is_atomic(tmp_path):
    path = tmp_path / "nested" / "wiki.json"
    _save_cache(path, [WebWikiDoc(title="тест", url="https://example.test", text="текст")])

    assert '"title": "тест"' in path.read_text(encoding="utf-8")
    assert not list(path.parent.glob(".*.tmp"))


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

    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self.closed = False

        def close(self):
            self.closed = True

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.close()
            return False

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
    assert clients and clients[0].closed


def test_sitemap_client_closes_when_request_fails(monkeypatch):
    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.closed = True
            return False

        def get(self, url):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.web_wiki_index.httpx.Client", Client)

    with pytest.raises(RuntimeError, match="network down"):
        _read_sitemap_urls(
            "https://wiki.test/sitemap.xml",
            max_pages=10,
            base_url="https://wiki.test",
        )

    assert clients and clients[0].closed


def test_fetch_docs_client_closes_when_unexpected_error(monkeypatch):
    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.closed = True
            return False

        def get(self, url):
            raise KeyboardInterrupt

    monkeypatch.setattr("app.web_wiki_index.httpx.Client", Client)

    with pytest.raises(KeyboardInterrupt):
        _fetch_docs(["https://wiki.test/page"])

    assert clients and clients[0].closed
