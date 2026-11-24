import pandas as pd

import peaks
import t212_history_rebuild
import xtb_history_rebuild


def test_series_peak_returns_max_and_day():
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    assert peaks.series_peak(pd.Series([1.0, 5.0, 3.0, 0.0], index=idx)) == (5.0, "2026-01-02")
    assert peaks.series_peak(pd.Series([0.0, 0.0], index=idx[:2])) is None
    assert peaks.series_peak(pd.Series([], dtype=float)) is None


def test_portfolio_peak_history_and_current():
    recs = [{"ts": "2026-10-01T23:00:00", "market_value": 100.0},
            {"ts": "2026-11-02T10:15:00", "market_value": 150.0},
            {"ts": "2026-11-03T10:15:00", "market_value": 120.0}]
    pk = peaks.portfolio_peak(recs, current=130.0)
    assert pk["value"] == 150.0 and pk["ts"] == "2026-11-02T10:15:00" and not pk["now"]
    assert peaks.portfolio_peak(recs, current=160.0)["now"]
    assert peaks.portfolio_peak([], current=None) is None


def test_portfolio_low_uses_latest_uninterrupted_native_cost_basis():
    from history_multi import multi_history_records
    from unittest.mock import patch

    raw = [
        {"ts": "2026-11-22T12:00:00", "entries": {"XTB": {"ccy": "USD", "cost": 500, "value": 20}}, "rates": {"EUR": 1, "USD": .9}},
        {"ts": "2026-11-23T11:40:00", "entries": {"XTB": {"ccy": "USD", "cost": 100, "value": 120}}, "rates": {"EUR": 1, "USD": .9}},
        {"ts": "2026-11-23T11:55:00", "entries": {"XTB": {"ccy": "USD", "cost": 500, "value": 520}}, "rates": {"EUR": 1, "USD": .9}},
        {"ts": "2026-11-23T12:10:00", "entries": {"XTB": {"ccy": "USD", "cost": 500, "value": 560}}, "rates": {"EUR": 1, "USD": .92}},
    ]
    with patch("history_multi._merged_history", return_value=raw):
        records = multi_history_records(["XTB"], "EUR", include_cost_basis=True)
    assert records[-2]["invested"] != records[-1]["invested"]
    assert peaks.portfolio_low(records) == {
        "value": 468.0, "ts": "2026-11-23T11:55:00", "start": "2026-11-23T11:55:00",
    }


def test_portfolio_low_native_history_without_cost_basis():
    records = [
        {"date": "2026-11-22", "invested": 200, "market_value": 250},
        {"date": "2026-11-23", "invested": 600, "market_value": 620},
        {"date": "2026-11-24", "invested": 600, "market_value": 605},
    ]
    assert peaks.portfolio_low(records) == {"value": 605.0, "ts": "2026-11-24", "start": "2026-11-23"}


def test_peak_label_daily_vs_intraday():
    # o zi reconstruita ramane ziua ei (nu trece in ziua urmatoare la conversia fusului)
    assert peaks.peak_label("2026-10-01T23:00:00") == "01.10.2026"
    assert peaks.peak_label("2026-11-02T10:15:00") == "02.11.2026 10:15"


def test_position_peaks_matches_ticker_or_symbol(monkeypatch):
    monkeypatch.setattr(t212_history_rebuild, "load_peaks", lambda: {
        "AAPL_US_EQ": [{"label": "Trading 212", "ccy": "EUR", "sym": "AAPL", "value": 500.0, "date": "2026-09-01"}]})
    monkeypatch.setattr(xtb_history_rebuild, "load_peaks", lambda: {
        "AAPL.US": [{"label": "XTB EUR", "ccy": "EUR", "sym": "AAPL", "value": 300.0, "date": "2026-08-01"}],
        "MSFT.US": [{"label": "XTB EUR", "ccy": "EUR", "sym": "MSFT", "value": 900.0, "date": "2026-08-01"}]})
    found = peaks.position_peaks("AAPL_US_EQ", "AAPL", {"XTB EUR": 350.0, "Trading 212": 400.0})
    assert [(p["label"], p["value"], p["now"]) for p in found] == [
        ("Trading 212", 500.0, False), ("XTB EUR", 350.0, True)]
