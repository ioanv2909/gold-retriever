from datetime import date

import pandas as pd
import pytest

import strategies as s

TODAY = date(2026, 6, 1)
YEARS = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]


def frame(rows):
    return pd.DataFrame(rows, index=YEARS).T


def statements(better=True):
    """Doi ani in care toate cele noua teste Piotroski trec (better=True) sau pica."""
    k = 1 if better else -1
    fin = frame({
        "Net Income": [120 if better else -10, 100, 90, 80],
        "Total Revenue": [1000 + 100 * k, 1000, 950, 900],
        "Gross Profit": [500 + 100 * k, 500, 470, 450],
        "Diluted EPS": [6.0, 5.0, 4.5, 4.0],
    })
    bs = frame({
        "Total Assets": [1000 - 50 * k, 1000, 980, 960],
        "Current Assets": [400 + 40 * k, 400, 390, 380],
        "Current Liabilities": [200, 200, 200, 200],
        "Long Term Debt": [300 - 30 * k, 300, 300, 300],
        "Ordinary Shares Number": [20 - k, 20, 20, 20],
        "Stockholders Equity": [500, 480, 460, 440],
    })
    cf = frame({"Operating Cash Flow": [150 if better else -20, 130, 120, 110], "Free Cash Flow": [110, 100, 90, 80]})
    return fin, bs, cf


def test_piotroski_all_pass_and_all_fail():
    assert s.piotroski(*statements(True)) == (9, 9)
    passed, n = s.piotroski(*statements(False))
    assert n == 9 and passed == 0


def test_piotroski_skips_missing_tests():
    fin, bs, cf = statements(True)
    bs = bs.drop(["Current Assets", "Current Liabilities"])
    fin = fin.drop(["Gross Profit"])
    assert s.piotroski(fin, bs, cf) == (7, 7)


def test_ddm_two_stage_equals_gordon_with_constant_growth():
    d0, r, g = 2.0, 8.0, 3.0
    assert s.ddm_value(d0, r, g, g) == pytest.approx(d0 * 1.03 / 0.05)
    assert s.ddm_value(d0, 3.0, 2.0, 3.0) is None


def div_metrics(**kw):
    annual = {str(y): 1.0 * 1.06 ** (y - 2010) for y in range(2010, 2026)}  # 16 ani, +6% pe an
    m = {"kind": "stock", "annual_div": annual, "price": 60.0, "rf": 4.0, "beta": 0.8, "roe": 20.0, "payout": 50.0,
         "div_yield": 3.5, "eps_hist": {"2023": 4.0, "2024": 4.3, "2025": 4.6}}
    m.update(kw)
    return m


def test_ddm_lens_uses_capm_and_lowest_growth():
    r = s.ddm_lens(div_metrics(), today=TODAY)
    x = r["extra"]
    assert x["r"] == pytest.approx(4.0 + 0.8 * s.ERP)
    assert x["g1"] == pytest.approx(6.0, abs=0.01)  # min(CAGR 6%, ROE*(1-payout) = 10%)
    assert x["g2"] == s.TERMINAL_G
    assert x["value"] == pytest.approx(s.ddm_value(x["d0"], x["r"], x["g1"], x["g2"]))
    assert x["margin"] == pytest.approx((x["value"] / 60 - 1) * 100)
    sens = x["sens"]
    assert sens["0,0"] == pytest.approx(x["value"])
    assert sens["1,0"] < sens["0,0"] < sens["-1,0"]   # randament cerut mai mare -> valoare mai mica
    assert sens["0,-1"] < sens["0,0"] < sens["0,1"]
    assert r["level"] in ("strong", "mixed", "weak") and r["coverage"] == 100


@pytest.mark.parametrize("kw, reason", [
    ({"annual_div": {}}, "no_dividend"),
    ({"annual_div": {"2023": 1.0, "2024": 1.0, "2025": 1.0}}, "short_history"),
    ({"div_yield": 0.5}, "low_yield"),
    ({"price": 10000.0}, "units"),
    ({"annual_div": {str(y): (4.0 if y < 2018 else 2.0 if y < 2022 else 1.0) for y in range(2010, 2026)},
      "price": 20.0}, "irregular"),
])
def test_ddm_not_applicable(kw, reason):
    r = s.ddm_lens(div_metrics(**kw), today=TODAY)
    assert not r["applicable"] and r["reason"] == reason and r["level"] == "na"


def test_div_growth_lens():
    r = s.div_growth_lens(div_metrics(), today=TODAY)
    vals = {row["key"]: row["value"] for row in r["rows"]}
    assert vals["growth_streak"] == 15
    assert vals["dgr_5y"] == pytest.approx(6.0, abs=0.01) and vals["dgr_10y"] == pytest.approx(6.0, abs=0.01)
    assert vals["chowder"] == pytest.approx(9.5, abs=0.01)
    # payout 2023 -> 2025: dividendul creste cu 6%/an, EPS cu 7%/an, deci payout-ul scade
    assert vals["payout_trend"] == pytest.approx((1.06 ** 15 / 4.6 - 1.06 ** 13 / 4.0) * 100 / 2)
    chowder = next(row for row in r["rows"] if row["key"] == "chowder")
    assert chowder["target"] == 12  # randament >= 3%
    low = s.div_growth_lens(div_metrics(div_yield=1.5), today=TODAY)
    assert next(row for row in low["rows"] if row["key"] == "chowder")["target"] == 15
    assert s.div_growth_lens(div_metrics(annual_div={}), today=TODAY)["reason"] == "no_dividend"


def test_growth_streak_stops_at_flat_year():
    annual = {2020: 1.0, 2021: 1.1, 2022: 1.1, 2023: 1.2, 2024: 1.3, 2025: 1.4}
    assert s.growth_streak(annual, 2025) == 3


def test_value_lens_flags_value_trap():
    cheap = {"pe_vs_hist": 0.6, "fcf_yield": 9.0, "ey_spread": 5.0, "graham_upside": 30.0, "piotroski": 8, "piotroski_n": 9,
             "ev_ebitda": 6.0}
    assert s.value_lens(cheap)["level"] == "strong"
    assert s.value_lens(cheap, quality=80)["level"] == "strong"
    assert s.value_lens(cheap, quality=40)["level"] == "trap"
    thin = s.value_lens({"ev_ebitda": 6.0})
    assert thin["level"] == "insufficient" and thin["coverage"] == 10


def test_evaluate_and_convergence():
    etf = s.evaluate({"kind": "etf"})
    assert all(r["reason"] == "etf" for r in etf.values()) and s.convergence(etf) == (0, 0, 0)
    assert all(r["reason"] == "no_data" for r in s.evaluate(None).values())
    res = {"a": {"level": "strong"}, "b": {"level": "trap"}, "c": {"level": "mixed"}, "d": {"level": "na"},
           "e": {"level": "insufficient"}, "f": {"level": "weak"}}
    assert s.convergence(res) == (1, 2, 4)


class FakeTicker:
    def __init__(self, quote="EQUITY", currency="USD", fin_ccy="USD"):
        self.info = {"quoteType": quote, "currency": currency, "financialCurrency": fin_ccy, "currentPrice": 100.0,
                     "trailingPE": 20.0, "enterpriseToEbitda": 12.0, "trailingPegRatio": 1.5, "dividendYield": 2.0,
                     "payoutRatio": 0.4, "returnOnEquity": 0.25, "beta": 1.1}
        self.financials, self.balance_sheet, self.cashflow = statements(True)
        self.dividends = pd.Series([0.5, 0.5, 0.55, 0.55],
                                   index=pd.to_datetime(["2024-03-01", "2024-09-01", "2025-03-01", "2025-09-01"]))
        self.revenue_estimate = pd.DataFrame({"avg": [1.0, 1.0], "growth": [0.08, 0.10]}, index=["0y", "+1y"])
        self.earnings_estimate = pd.DataFrame({"avg": [1.0, 1.0], "growth": [0.12, 0.15]}, index=["0y", "+1y"])
        self.eps_trend = pd.DataFrame({"current": [5.5], "30daysAgo": [5.4], "90daysAgo": [5.0]}, index=["0y"])

    def history(self, period, interval, auto_adjust):
        idx = pd.date_range("2021-01-31", "2026-05-31", freq="ME")
        return pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)


def test_extract_metrics_from_yahoo_shapes():
    m = s.extract_metrics(FakeTicker(), rf=4.0, today=TODAY)
    assert m["kind"] == "stock" and m["v"] == s.VERSION
    assert m["pe_hist"] == pytest.approx((100 / 4.5 + 100 / 5.0) / 2)  # mediana P/E 25, 22.2, 20, 16.7
    assert m["fcf_yield"] == pytest.approx(110 / 19 / 100 * 100)
    assert m["ey_spread"] == pytest.approx(5.0 - 4.0)
    assert m["piotroski"] == 9 and m["piotroski_n"] == 9
    assert m["rev_growth_fwd"] == pytest.approx(10.0) and m["eps_growth_fwd"] == pytest.approx(15.0)
    assert m["eps_rev_90d"] == pytest.approx(10.0)
    assert m["rule_of_40"] == pytest.approx(10.0 + 10.0)
    assert m["annual_div"] == {"2024": 1.0, "2025": 1.1}
    assert m["payout"] == pytest.approx(40.0) and m["roe"] == pytest.approx(25.0)
    import json
    json.dumps(m)


def test_extract_metrics_skips_price_ratios_across_currencies():
    m = s.extract_metrics(FakeTicker(currency="USD", fin_ccy="DKK"), rf=4.0, today=TODAY)
    assert m["pe_hist"] is None and m["fcf_yield"] is None and m["graham_upside"] is None
    gbp = s.extract_metrics(FakeTicker(currency="GBp", fin_ccy="GBP"), rf=4.0, today=TODAY)
    assert gbp["fcf_yield"] == pytest.approx(110 / 19 / 1.0 * 100)  # 100 pence = 1 GBP
    assert s.extract_metrics(FakeTicker(quote="ETF")) == {"v": s.VERSION, "kind": "etf"}


def test_fetch_and_cache_refreshes_only_stale(monkeypatch):
    calls = []

    def fetch(symbol, rf):
        calls.append((symbol, rf))
        return ({"kind": "etf"}, None) if symbol == "E" else (None, "boom")

    s.fetch_and_cache(["E", "X"], resolve=str, now=1000.0, sleep=0, fetch=fetch, rf_fn=lambda: 4.2)
    cache = s.load_cache()
    assert calls == [("E", 4.2), ("X", 4.2)]
    assert cache["E"]["m"] == {"kind": "etf"} and cache["X"]["error"] == "boom"
    assert s.load_status()["in_progress"] is False

    calls.clear()
    s.fetch_and_cache(["E", "X"], resolve=str, now=2000.0, sleep=0, fetch=fetch, rf_fn=lambda: 4.2)
    assert calls == []
    s.fetch_and_cache(["E"], resolve=str, now=1000.0 + s.STRATEGY_REFRESH_INTERVAL, sleep=0, fetch=fetch,
                      rf_fn=lambda: 4.2)
    assert calls == [("E", 4.2)]


def test_piotroski_scaled_to_nine_only_with_enough_tests():
    rows = lambda m: {r["key"]: r["value"] for r in s.value_lens(m)["rows"]}
    assert rows({"piotroski": 6, "piotroski_n": 6})["piotroski"] == pytest.approx(9.0)
    assert rows({"piotroski": 4, "piotroski_n": 5})["piotroski"] is None


def _metrics():
    m = div_metrics(pe=12.0, pe_hist=15.0, pe_vs_hist=0.8, fcf_yield=7.0, ey_spread=4.0, graham_upside=10.0,
                    piotroski=7, piotroski_n=9, ev_ebitda=9.0, rev_cagr=6.0, eps_cagr=8.0, peg=1.4)
    m.update(v=s.VERSION)
    return m


def _tab_page():
    import pandas as pd
    from strategies_ui import render_strategies_tab
    render_strategies_tab(pd.DataFrame([{"ticker": "AAA", "name": "Alpha"}, {"ticker": "EEE", "name": "Etf"},
                                        {"ticker": "NEW", "name": "New"}]))


def _section_page():
    from strategies_ui import render_strategy_section
    render_strategy_section("AAA", "AAA", {"averagePrice": 40.0, "currentPrice": 60.0})


def _ui_setup(monkeypatch):
    import background
    from core import save_json_file
    monkeypatch.setattr(background, "load_quality_cache", lambda: {})
    save_json_file(s.STRATEGY_CACHE_FILE, {
        "AAA": {"symbol": "AAA", "fetched_at": 1.0, "v": s.VERSION, "m": _metrics()},
        "EEE": {"symbol": "EEE", "fetched_at": 1.0, "v": s.VERSION, "m": {"v": s.VERSION, "kind": "etf"}},
    })


def test_strategies_tab_renders_matrix(monkeypatch):
    from streamlit.testing.v1 import AppTest
    _ui_setup(monkeypatch)
    at = AppTest.from_function(_tab_page).run()
    assert not at.exception
    df = at.dataframe[0].value
    assert list(df["ticker"]) == ["AAA", "EEE", "NEW"]
    assert df.loc[0, "value"] is not None and "pozitive" in df.loc[0, "conv"]
    assert df.loc[1, "conv"] == "Nu se aplică la ETF-uri" and df.loc[2, "conv"].startswith("Fără date")


def test_strategy_section_renders_cards_and_ddm(monkeypatch):
    from streamlit.testing.v1 import AppTest
    _ui_setup(monkeypatch)
    at = AppTest.from_function(_section_page).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Valoare DDM" in text and "/100" in text
    captions = " ".join(c.value for c in at.caption)
    assert "yield on cost" in captions and "5.25" in captions  # 3.5% x 60 / 40


def test_score_shade_darkens_with_the_score():
    from strategies_ui import _shade
    assert _shade(None) == "" and _shade(float("nan")) == ""
    shades = [_shade(v) for v in (10, 40, 55, 70, 95)]
    assert len(set(shades)) == 5 and "#1f7a4d" in shades[-1] and "#eef7f1" in shades[0]
