"""Coloanele calculate ale pozitiilor de pe pagina principala (positions_data, fara UI)."""
import pandas as pd
import pytest

import positions_data
from positions_data import build_t212_frame, div_score, enrich_view, finish_t212_frame


@pytest.fixture(autouse=True)
def _fx(monkeypatch):
    rates = {("USD", "EUR"): 0.5, ("GBP", "EUR"): 1.2}
    monkeypatch.setattr(positions_data, "fetch_fx_rate", lambda a, b: (rates.get((a, b), 1.0), None))


def _positions():
    return [
        {"ticker": "AAPL_US_EQ", "quantity": 2.0, "averagePrice": 100.0, "currentPrice": 150.0, "ppl": 50.0,
         "initialFillDate": "2024-01-02T10:00:00.000+02:00"},
        {"ticker": "VOD_L_EQ", "quantity": 10.0, "averagePrice": 1000.0, "currentPrice": 1100.0, "ppl": 10.0,
         "initialFillDate": "2024-01-02T10:00:00.000+02:00"},
    ]


def _instruments():
    return [{"ticker": "AAPL_US_EQ", "name": "Apple", "currencyCode": "USD"},
            {"ticker": "VOD_L_EQ", "name": "vodafone", "currencyCode": "GBX"}]


def test_div_score_needs_half_coverage():
    assert div_score(None) is None
    assert div_score({"div_total": 71.26, "div_coverage": 40}) is None
    assert div_score({"div_total": 71.26, "div_coverage": 50}) == 71.3


def test_frame_converts_gbx_and_values_in_account_currency():
    df, fx_errors, total, total_div = build_t212_frame(
        _positions(), _instruments(), None, "EUR",
        {"AAPL_US_EQ": {"total": 10.0}}, {"AAPL_US_EQ": "buy"}, {"AAPL_US_EQ": {"total": 72.44, "rating": "A"}})
    vod = df[df["ticker"] == "VOD_L_EQ"].iloc[0]
    assert vod["currencyCode"] == "GBP" and vod["currentPrice"] == pytest.approx(11.0)
    aapl = df[df["ticker"] == "AAPL_US_EQ"].iloc[0]
    assert aapl["randament_%"] == pytest.approx(50.0)
    assert aapl["cost_achizitie_cont"] == pytest.approx(100.0)       # 200 USD * 0.5
    assert aapl["div_pe_investit_%"] == pytest.approx(10.0)
    assert aapl["randament_total_%"] == pytest.approx(60.0)
    assert aapl["recomandare"] == "buy" and aapl["Scor"] == 72.4
    assert vod["recomandare"] == "none" and pd.isna(vod["Scor"])
    assert total == pytest.approx(300 * 0.5 + 110 * 1.2)
    assert total_div == pytest.approx(10.0) and fx_errors == []


def test_frame_without_positions_or_instruments():
    df, _, total, total_div = build_t212_frame([], None, None, "EUR", {}, {}, {})
    assert df.empty and total == 0 and total_div == 0
    assert {"name", "currencyCode", "randament_total_%", "Scor div."} <= set(df.columns)


def test_finish_sorts_by_name_and_compares_with_sp500():
    df, *_ = build_t212_frame(_positions(), _instruments(), None, "EUR", {}, {}, {})
    df = finish_t212_frame(df, {"AAPL_US_EQ": {"sp500_return_%": 20.0, "peg": 1.5}})
    assert list(df["name"]) == ["Apple", "vodafone"]                 # fara diferenta intre litere mari si mici
    assert df.loc[0, "alpha_%"] == pytest.approx(30.0)
    assert df.loc[0, "zile_detinut"] > 0


def test_enrich_view_hides_scores_with_low_coverage():
    vdf = pd.DataFrame({"ticker": ["A", "B"], "randament_total_%": [5.0, 1.0], "initialFillDate": [None, None]})
    quality = {"A": {"total": 80.04, "coverage": 60, "risk_total": 30.0, "risk_coverage": 40}, "B": {"total": 50.0, "coverage": 10}}
    out = enrich_view(vdf, {"A": "buy"}, {"A": {"upside": 12.5}}, quality, {"A": {"sp500_return_%": 2.0}})
    assert out.loc[0, "Scor"] == 80.0 and pd.isna(out.loc[0, "Scor risc"]) and pd.isna(out.loc[1, "Scor"])
    assert out.loc[0, "tinta_%"] == 12.5 and out.loc[1, "recomandare"] == "none"
    assert out.loc[0, "alpha_%"] == pytest.approx(3.0)
    assert "Scor" not in vdf.columns                                  # randurile primite nu se modifica
