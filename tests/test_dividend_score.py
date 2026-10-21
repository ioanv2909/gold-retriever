from datetime import date

import pandas as pd
import pytest

import dividend_score as ds

TODAY = date(2026, 10, 21)


def series(per_year):
    """Dividende trimestriale: {an: suma anuala}."""
    idx, vals = [], []
    for y, total in per_year.items():
        for q in (2, 5, 8, 11):
            idx.append(pd.Timestamp(y, q, 15))
            vals.append(total / 4)
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


def test_annual_dividends_skips_current_year():
    s = series({2024: 2.0, 2025: 2.2, 2026: 2.4})
    assert ds.annual_dividends(s, TODAY) == pytest.approx({2024: 2.0, 2025: 2.2})
    assert ds.annual_dividends(pd.Series(dtype=float), TODAY) == {}


def test_history_growth_streak_and_no_cuts():
    annual = {y: 1.0 * 1.07 ** (y - 2010) for y in range(2010, 2026)}
    m = ds.history_metrics(annual, TODAY)
    assert m["years_paid"] == 16
    assert m["div_cagr_5y"] == pytest.approx(7.0)
    assert m["cuts_10y"] == 0


def test_cut_over_two_calendar_years_counts_once():
    annual = {2018: 2.0, 2019: 2.04, 2020: 2.08, 2021: 2.08, 2022: 1.39, 2023: 1.11, 2024: 1.11, 2025: 1.11}
    m = ds.history_metrics(annual, TODAY)
    assert m["cuts_10y"] == 1
    assert m["div_cagr_5y"] < 0


def test_payment_moved_across_year_is_not_a_cut():
    # plata din decembrie 2022 a ajuns in ianuarie 2023: 3 plati, apoi 5
    annual = {2020: 4.0, 2021: 4.0, 2022: 3.0, 2023: 5.0, 2024: 4.0, 2025: 4.0}
    assert ds.history_metrics(annual, TODAY)["cuts_10y"] == 0


def test_streak_breaks_on_missing_year_and_stopped_dividend():
    assert ds.history_metrics({2019: 1, 2020: 1, 2022: 1, 2023: 1, 2024: 1, 2025: 1}, TODAY)["years_paid"] == 4
    assert ds.history_metrics({2023: 1, 2024: 1}, TODAY) == {"div_cagr_5y": None, "years_paid": None, "cuts_10y": None}


def test_yield_trap_lowers_score():
    assert ds.yield_score(3.0) == 1.0
    assert ds.yield_score(6.0) == 1.0
    assert ds.yield_score(12.0) == pytest.approx(0.5)
    assert ds.yield_score(0.5) == 0.0
    assert ds.yield_score(None) is None


def test_fcf_payout_from_cashflow():
    cf = pd.DataFrame({"2026": [66.9e9, -26.4e9], "2025": [71.6e9, -24.1e9]},
                      index=["Free Cash Flow", "Cash Dividends Paid"])
    assert ds.fcf_payout(cf) == pytest.approx(26.4 / 66.9 * 100)
    cf.loc["Free Cash Flow", "2026"] = -1e9
    assert ds.fcf_payout(cf) == 200.0
    assert ds.fcf_payout(pd.DataFrame()) is None


def test_compute_score_total_pillars_and_rating():
    good = {"payout_ratio": 50, "fcf_payout": 50, "div_cagr_5y": 8, "years_paid": 25, "cuts_10y": 0, "dividend_yield": 3.5}
    r = ds.compute_dividend_score(good)
    assert r["total"] == pytest.approx(100.0) and r["rating"] == "Excelent" and r["coverage"] == 100
    assert r["pillars"] == {"safety": 100.0, "growth": 100.0, "consistency": 100.0, "yield": 100.0}

    bad = dict(good, payout_ratio=120, fcf_payout=150, div_cagr_5y=-5, cuts_10y=2)
    r = ds.compute_dividend_score(bad)
    assert r["pillars"]["safety"] == 0 and r["pillars"]["growth"] == 0 and r["rating"] == "Respins"


def test_compute_score_partial_coverage():
    r = ds.compute_dividend_score({"dividend_yield": 3.0, "years_paid": 12})
    assert r["coverage"] == 30 and r["rating"] == "Date insuficiente"
    assert r["pillars"]["safety"] is None and r["pillars"]["yield"] == 100.0


class FakeTicker:
    def __init__(self, info, dividends, cashflow=None):
        self.info, self.dividends, self.cashflow = info, dividends, cashflow


def test_extract_detects_non_payer_and_payer():
    m, pays = ds.extract_dividend_metrics(FakeTicker({}, pd.Series(dtype=float)), TODAY)
    assert pays is False and m["dividend_yield"] is None

    tk = FakeTicker({"dividendRate": 2.0, "payoutRatio": 0.55, "dividendYield": 2.4},
                    series({y: 2.0 for y in range(2015, 2027)}))
    m, pays = ds.extract_dividend_metrics(tk, TODAY)
    assert pays is True
    assert m["payout_ratio"] == pytest.approx(55.0) and m["years_paid"] == 11 and m["fcf_payout"] is None
