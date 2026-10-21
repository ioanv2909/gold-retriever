import pandas as pd
import pytest

import analysts


def test_parse_targets_and_gbp_scale():
    raw = {"current": 4847.5, "high": 5933.8, "low": 3966.5, "mean": 5150.0, "median": 5101.7}
    t = analysts.parse_targets(raw, scale=100.0)
    assert t == pytest.approx({"low": 39.665, "mean": 51.5, "median": 51.017, "high": 59.338, "current": 48.475})
    assert analysts.parse_targets({}) is None
    assert analysts.parse_targets(None) is None
    assert analysts.parse_targets({"mean": float("nan")}) is None


def test_upside():
    assert analysts.upside(110, 100) == pytest.approx(10.0)
    assert analysts.upside(None, 100) is None
    assert analysts.upside(110, 0) is None


def test_parse_recommendations_skips_empty_months():
    df = pd.DataFrame([
        {"period": "0m", "strongBuy": 6, "buy": 18, "hold": 14, "sell": 3, "strongSell": 3},
        {"period": "-1m", "strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0},
    ])
    out = analysts.parse_recommendations(df)
    assert len(out) == 1 and out[0]["total"] == 44 and out[0]["period"] == "0m"
    assert analysts.parse_recommendations(None) == []


def test_parse_estimates_eps_and_revenue():
    eps = pd.DataFrame(
        {"avg": [1.978, 8.82], "low": [1.93, 8.28], "high": [2.06, 8.93], "yearAgoEps": [1.85, 7.46],
         "numberOfAnalysts": [27, 39], "growth": [0.0693, 0.1823], "currency": ["USD", "USD"]},
        index=["0q", "0y"])
    out = analysts.parse_estimates(eps)
    assert list(out) == ["0q", "0y"]
    assert out["0y"] == pytest.approx({"avg": 8.82, "low": 8.28, "high": 8.93, "n": 39, "year_ago": 7.46,
                                       "growth": 18.23, "currency": "USD"})
    rev = pd.DataFrame({"avg": [5e10], "low": [4.9e10], "high": [5.1e10], "yearAgoRevenue": [4.5e10],
                        "numberOfAnalysts": [10], "growth": [None], "currency": ["EUR"]}, index=["+1y"])
    out = analysts.parse_estimates(rev)
    assert out["+1y"]["year_ago"] == 4.5e10 and out["+1y"]["growth"] is None


def test_parse_estimates_converts_pence():
    df = pd.DataFrame({"avg": [250.0], "low": [240.0], "high": [260.0], "yearAgoEps": [200.0],
                       "numberOfAnalysts": [5], "growth": [0.25], "currency": ["GBp"]}, index=["0y"])
    e = analysts.parse_estimates(df)["0y"]
    assert e["avg"] == 2.5 and e["year_ago"] == 2.0 and e["currency"] == "GBP"


def test_parse_eps_trend_and_revisions():
    trend = pd.DataFrame({"current": [2.0], "7daysAgo": [2.0], "30daysAgo": [1.9], "60daysAgo": [1.9],
                          "90daysAgo": [2.5]}, index=["0y"])
    rev = pd.DataFrame({"upLast7days": [0], "upLast30days": [3], "downLast30days": [1], "downLast7Days": [0]},
                       index=["0y"])
    out = analysts.parse_eps_trend(trend, rev)
    assert out["0y"]["chg_30d"] == pytest.approx(5.263, abs=1e-3)
    assert out["0y"]["chg_90d"] == pytest.approx(-20.0)
    assert out["0y"]["up_30d"] == 3 and out["0y"]["down_30d"] == 1


def test_parse_rating_changes_newest_first():
    df = pd.DataFrame({
        "Firm": ["Old", "New"], "ToGrade": ["Buy", "Hold"], "FromGrade": ["", "Buy"], "Action": ["init", "down"],
        "priceTargetAction": ["", ""], "currentPriceTarget": [300.0, 330.0], "priorPriceTarget": [0.0, 370.0],
    }, index=pd.to_datetime(["2026-01-05 10:00", "2026-10-20 09:46"]))
    out = analysts.parse_rating_changes(df)
    assert [c["firm"] for c in out] == ["New", "Old"]
    assert out[0] == {"date": "2026-10-20", "firm": "New", "action": "down", "from": "Buy", "to": "Hold",
                      "target": 330.0, "prior_target": 370.0}
    assert out[1]["prior_target"] is None


class Boom:
    @property
    def analyst_price_targets(self):
        raise RuntimeError("404")

    recommendations = None
    earnings_estimate = revenue_estimate = eps_trend = eps_revisions = upgrades_downgrades = None


def test_fetch_tolerates_missing_parts():
    d = analysts.fetch_analyst_data(Boom())
    assert d["targets"] is None and d["recommendations"] == [] and not analysts.has_data(d)
