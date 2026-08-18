from __future__ import annotations

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
