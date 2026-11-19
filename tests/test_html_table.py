"""Tabelul HTML: escape, tooltip, legaturi, sigle."""
import html_table


def test_build_escapes_and_adds_tooltips_links_and_images():
    cols = [{"key": "logo", "label": ""}, {"key": "name", "label": "Nume", "help": "ajutor"}, {"key": "v", "label": "V", "align": "right"}]
    rows = [{"logo": {"img": "data:image/png;base64,AAA", "img_title": "AAPL"},
             "name": {"text": "<b>Apple</b>", "title": "AAPL_US_EQ", "href": html_table.detail_href("AAPL_US_EQ")},
             "v": {"text": "80/100", "style": "background-color: #0a0"}}]
    out = html_table.build(cols, rows)
    assert "&lt;b&gt;Apple&lt;/b&gt;" in out and "<b>Apple" not in out
    assert 'title="AAPL_US_EQ"' in out and 'href="?detail=AAPL_US_EQ"' in out and 'target="_self"' in out
    assert 'src="data:image/png;base64,AAA"' in out and 'title="ajutor"' in out and "text-align:right" in out


def test_detail_href_quotes_tickers():
    assert html_table.detail_href("A&B C") == "?detail=A%26B%20C"
