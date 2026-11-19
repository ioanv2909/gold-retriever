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


def test_sortable_headers_and_column_ids():
    cols = [{"key": "logo", "label": ""}, {"key": "name", "label": "Nume"}, {"key": "v", "label": "Scor", "sortable": False}]
    out = html_table.build(cols, [{"name": "A", "v": {"text": "80/100", "sort": 80}}], tid="t1", cols_label="Coloane")
    assert 'data-tid="t1"' in out and 'data-cols-label="Coloane"' in out
    assert 'data-key="name" data-label="Nume" data-sortable="1"' in out
    assert 'data-key="logo" data-label="" data-sortable="0"' in out and 'data-key="v" data-label="Scor" data-sortable="0"' in out
    assert 'data-sort="80"' in out
    assert "data-tid" not in html_table.build(cols, [])  # fara tid: tabel static


def test_render_adds_the_browser_script_only_with_an_id():
    from streamlit.testing.v1 import AppTest

    def page():
        import html_table
        html_table.render([{"key": "a", "label": "A"}], [{"a": 1}], tid="x")

    at = AppTest.from_function(page).run()
    assert not at.exception
    assert any("grtbl" in m.value for m in at.markdown)
