import numpy as np
import pandas as pd
import pytest

import compare


def test_normalize_from_first_valid_price():
    idx = pd.date_range("2026-01-01", periods=4)
    closes = pd.DataFrame({"A": [100.0, 110.0, 90.0, 120.0], "B": [np.nan, 50.0, 55.0, 45.0]}, index=idx)
    n = compare.normalize(closes)
    assert list(n["A"].round(6)) == [0.0, 10.0, -10.0, 20.0]
    assert n["B"].dropna().round(6).tolist() == [0.0, 10.0, -10.0]
    assert compare.normalize(pd.DataFrame()).empty


def test_period_stats():
    s = pd.Series([100.0, 120.0, 90.0, 99.0, 108.0, 110.0])
    st = compare.period_stats(s)
    assert st["return"] == pytest.approx(10.0)
    assert st["max_drawdown"] == pytest.approx(-25.0)
    rets = s.pct_change().dropna()
    assert st["volatility"] == pytest.approx(rets.std() * np.sqrt(252) * 100)
    assert compare.period_stats(pd.Series([100.0]))["return"] is None
    assert compare.period_stats(s.iloc[:3])["volatility"] is None
    assert compare.period_stats(s, interval="15m")["volatility"] is None


def test_closes_from_download_multi_and_single():
    idx = pd.date_range("2026-01-01", periods=2)
    multi = pd.DataFrame({("Close", "AAPL"): [1.0, 2.0], ("Close", "KO"): [3.0, 4.0], ("Open", "AAPL"): [0, 0]}, index=idx)
    multi.columns = pd.MultiIndex.from_tuples(multi.columns)
    out = compare.closes_from_download(multi, ["KO", "AAPL", "MISSING"])
    assert list(out.columns) == ["KO", "AAPL"]
    single = pd.DataFrame({"Close": [1.0, 2.0], "Open": [0, 0]}, index=idx)
    assert list(compare.closes_from_download(single, ["NVDA"]).columns) == ["NVDA"]
    assert compare.closes_from_download(None, ["X"]).empty


def test_fundamentals_converts_pence_and_target():
    f = compare.fundamentals({"currency": "GBp", "currentPrice": 4850.0, "targetMeanPrice": 5335.0,
                              "quoteType": "EQUITY", "trailingPE": "bad", "dividendYield": 3.1, "shortName": "Unilever"})
    assert f["currency"] == "GBP" and f["price"] == 48.5
    assert f["target_upside"] == pytest.approx(10.0)
    assert f["pe"] is None and f["dividend_yield"] == 3.1 and f["kind"] == "stock" and f["name"] == "Unilever"
    assert compare.fundamentals({"quoteType": "ETF"})["kind"] == "etf"
    assert compare.fundamentals(None)["target_upside"] is None


def test_parse_symbols():
    assert compare.parse_symbols("nvda, sap.de;KO  nvda") == ["NVDA", "SAP.DE", "KO"]
    assert compare.parse_symbols("") == []
    assert compare.parse_symbols("X" * 16) == []
