from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import market_hours as mh

BUC = ZoneInfo("Europe/Bucharest")


def test_exchange_of():
    assert mh.exchange_of("AAPL") == ""
    assert mh.exchange_of("BRK.B") == ""
    assert mh.exchange_of("VUSA.L") == ".L"
    assert mh.exchange_of("SAP.DE") == ".DE"
    assert mh.exchange_of("EURUSD=X") is None
    assert mh.exchange_of("^GSPC") is None
    assert mh.exchange_of("BTC-USD") is None
    assert mh.exchange_of("X.XYZ") is None
    assert mh.exchange_of(None) is None


def test_us_session_in_bucharest_time():
    start = datetime(2026, 11, 4, tzinfo=BUC)  # miercuri, dupa trecerea la ora de iarna in ambele tari
    end = datetime(2026, 11, 5, tzinfo=BUC)
    (a, b), = mh.sessions_between("", start, end)
    assert (a.hour, a.minute, b.hour) == (16, 30, 23)


def test_tokyo_has_lunch_break_and_weekend_is_empty():
    start = datetime(2026, 11, 4, tzinfo=BUC)
    end = datetime(2026, 11, 5, tzinfo=BUC)
    assert len(mh.sessions_between(".T", start, end)) == 2
    sat = datetime(2026, 11, 7, tzinfo=BUC)
    assert mh.sessions_between(".DE", sat, datetime(2026, 11, 8, tzinfo=BUC)) == []


def test_status_open_and_next_open_after_weekend():
    is_open, change = mh.status(".DE", datetime(2026, 11, 4, 12, 0, tzinfo=BUC))
    assert is_open and (change.hour, change.minute) == (18, 30)
    is_open, change = mh.status(".DE", datetime(2026, 11, 6, 20, 0, tzinfo=BUC))  # vineri seara
    assert not is_open and change.weekday() == 0 and change.hour == 10


def test_group_positions():
    groups, unknown = mh.group_positions([
        {"ticker": "AAPL_US_EQ", "name": "Apple", "yahoo_symbol": "AAPL"},
        {"ticker": "VUSAl_EQ", "name": "Vanguard S&P 500", "yahoo_symbol": "VUSA.L"},
        {"ticker": "ZZZ", "name": "Z", "yahoo_symbol": "ZZZ.QQ"}])
    assert groups == {"": ["Apple"], ".L": ["Vanguard S&P 500"]}
    assert unknown == ["ZZZ"]


def test_render_tab_smoke(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def app():
        import pandas as pd
        from market_hours_ui import render_market_hours_tab
        render_market_hours_tab(pd.DataFrame([
            {"ticker": "AAPL_US_EQ", "name": "Apple", "yahoo_symbol": "AAPL"},
            {"ticker": "7203.T", "name": "Toyota", "yahoo_symbol": "7203.T"},
            {"ticker": "FX", "name": "FX", "yahoo_symbol": "EURUSD=X"}]))

    at = AppTest.from_function(app).run()
    assert not at.exception
    assert len(at.dataframe) == 1
    assert any("FX" in c.value for c in at.caption)


def test_group_by_hours_merges_same_european_hours():
    day = datetime(2026, 11, 4, tzinfo=BUC)
    now = datetime(2026, 11, 4, 12, 0, tzinfo=BUC)
    bars = mh.group_by_hours({".DE": ["SAP"], ".PA": ["LVMH", "Total"], ".L": ["VUSA"], ".SW": ["Nestle"],
                               "": ["Apple"]}, day, now)
    # Londra 08:00-16:30 = 10:00-18:30 ora Romaniei, ca Xetra si SIX (calendarul: 09:00-17:30)
    assert [b["exchanges"] for b in bars] == [["Xetra", "Euronext Paris", "London", "SIX Swiss"], ["NYSE / Nasdaq"]]
    assert bars[0]["positions"] == 5 and bars[0]["open"] and not bars[1]["open"]


def test_group_by_hours_weekend_has_no_sessions():
    day = datetime(2026, 11, 7, tzinfo=BUC)
    bars = mh.group_by_hours({".DE": ["SAP"]}, day, datetime(2026, 11, 7, 12, 0, tzinfo=BUC))
    assert bars[0]["sessions"] == [] and not bars[0]["open"]


def test_render_strip_smoke():
    from streamlit.testing.v1 import AppTest

    def app():
        import pandas as pd
        from market_hours_ui import render_market_strip
        render_market_strip(pd.DataFrame([
            {"ticker": "SAP", "name": "SAP", "yahoo_symbol": "SAP.DE"},
            {"ticker": "MC", "name": "LVMH", "yahoo_symbol": "MC.PA"},
            {"ticker": "AAPL_US_EQ", "name": "Apple", "yahoo_symbol": "AAPL"}]))

    at = AppTest.from_function(app).run()
    assert not at.exception
    html_out = "".join(m.value for m in at.markdown)
    assert "Xetra, Euronext Paris" in html_out and "gr-mh-now" in html_out


def _rows():
    return pd.DataFrame([{"ticker": "SAP", "name": "SAP", "yahoo_symbol": "SAP.DE"},
                         {"ticker": "AAPL_US_EQ", "name": "Apple", "yahoo_symbol": "AAPL"}])


def test_market_bands_under_x_axis_on_short_range():
    import plotly.graph_objects as go
    from market_hours_ui import add_market_bands, BAND_ROW_PX, BAND_GAP_PX, BAND_AXIS_PX
    fig = go.Figure()
    x1 = pd.Timestamp.now()
    h = add_market_bands(fig, _rows(), x1 - pd.Timedelta(weeks=1), x1, 300)
    assert h == 300 + 2 * (BAND_ROW_PX + BAND_GAP_PX) + BAND_AXIS_PX
    assert fig.layout.yaxis.domain[0] > 0
    assert len(fig.layout.annotations) == 2
    assert all(s.y1 <= fig.layout.yaxis.domain[0] for s in fig.layout.shapes)
    assert len(fig.layout.shapes) >= 2 + 2 * 4  # 2 fundaluri + cel putin 4 sesiuni pe bursa intr-o saptamana


def test_market_bands_long_range_only_status():
    import plotly.graph_objects as go
    from market_hours_ui import add_market_bands
    fig = go.Figure()
    x1 = pd.Timestamp.now()
    assert add_market_bands(fig, _rows(), x1 - pd.Timedelta(days=365), x1, 300) == 300
    assert not fig.layout.shapes and "Europ" in fig.layout.annotations[0].text


def test_reference_day_skips_weekend():
    assert mh.reference_day(datetime(2026, 11, 7, 15, 0, tzinfo=BUC)).date().isoformat() == "2026-11-09"
    assert mh.reference_day(datetime(2026, 11, 4, 15, 0, tzinfo=BUC)).date().isoformat() == "2026-11-04"


def _day(y, m, d):
    return datetime(y, m, d, tzinfo=BUC), datetime(y, m, d, tzinfo=BUC) + __import__("datetime").timedelta(days=1)


def test_holidays_and_half_days_from_calendar():
    from datetime import date
    assert mh.sessions_between("", *_day(2026, 11, 26)) == []  # Thanksgiving
    assert mh.day_note("", date(2026, 11, 26)) == "holiday"
    (a, b), = mh.sessions_between("", *_day(2026, 11, 27))  # zi scurta: 9:30-13:00 la New York
    assert (a.hour, a.minute, b.hour) == (16, 30, 20)
    assert mh.day_note("", date(2026, 11, 27)) == "early"
    assert mh.sessions_between(".RO", *_day(2026, 12, 1)) == []  # Ziua Nationala
    assert mh.day_note(".DE", date(2026, 11, 4)) is None


def test_holiday_exchange_gets_its_own_bar():
    day = datetime(2026, 12, 1, tzinfo=BUC)
    bars = mh.group_by_hours({".DE": ["SAP"], ".RO": ["TLV"]}, day, datetime(2026, 12, 1, 12, 0, tzinfo=BUC))
    assert [b["exchanges"] for b in bars] == [["Xetra"], ["București"]]
    assert bars[1]["sessions"] == [] and bars[1]["notes"] == {"holiday"}


def test_static_fallback_without_calendar(monkeypatch):
    monkeypatch.setattr(mh, "_calendar_day", lambda *a: None)
    assert len(mh.sessions_between("", *_day(2026, 11, 26))) == 1
    assert mh.day_note("", __import__("datetime").date(2026, 11, 26)) is None


def test_frankfurt_keeps_its_own_hours():
    (a, b), = mh.sessions_between(".F", *_day(2026, 11, 4))
    assert (a.hour, b.hour) == (9, 23)
