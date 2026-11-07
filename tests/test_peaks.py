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
