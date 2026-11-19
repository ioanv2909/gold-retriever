"""Tabul Calendar: nume + sigla, ticker ca tooltip, simboluri si legenda."""
from datetime import date, timedelta


def _page():
    import events_ui
    events_ui.render_calendar_tab({"AAA_US_EQ": "Alpha Corp", "BBB_US_EQ": "Beta Inc"})


def test_calendar_shows_names_logos_icons_and_legend(monkeypatch):
    import events
    from streamlit.testing.v1 import AppTest
    soon = (date.today() + timedelta(days=3)).isoformat()
    rows = [{"ticker": "AAA_US_EQ", "type": "earnings", "date": soon, "days": 3, "eps_avg": 1.5},
            {"ticker": "BBB_US_EQ", "type": "ex_dividend", "date": soon, "days": 3}]
    monkeypatch.setattr(events, "upcoming", lambda cache, tickers, days=30: rows)
    monkeypatch.setattr(events, "load_cache", lambda: {})
    monkeypatch.setattr(events, "load_status", lambda: {})
    at = AppTest.from_function(_page).run()
    assert not at.exception
    html = next(m.value for m in at.markdown if "grtbl" in m.value)
    assert "Alpha Corp" in html and 'title="AAA_US_EQ"' in html and ">AAA_US_EQ<" not in html
    assert "📊" in html and "✂️" in html and "grtbl-logo" in html
    assert any("Ce înseamnă" in e.label for e in at.expander)
