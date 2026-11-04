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
