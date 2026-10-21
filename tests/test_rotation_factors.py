import numpy as np
import pandas as pd
import pytest

import factors
import rotation

WEEKS = pd.date_range("2024-10-21", periods=104, freq="W-MON")


def sector_prices():
    t = np.arange(104)
    spy = 100 * np.exp(0.002 * t)
    data = {"SPY": spy}
    for sector, etf in rotation.SECTOR_ETFS.items():
        data[etf] = spy  # la fel ca piata
    data["XLK"] = spy * np.exp(0.00002 * t ** 2)      # avans care accelereaza
    data["XLU"] = spy * np.exp(-0.00002 * t ** 2)     # ramane in urma tot mai repede
    return pd.DataFrame(data, index=WEEKS)


@pytest.mark.parametrize("ratio, mom, q", [(101, 101, "leading"), (101, 99, "weakening"), (99, 99, "lagging"),
                                           (99, 101, "improving")])
def test_quadrant(ratio, mom, q):
    assert rotation.quadrant(ratio, mom) == q


def test_rrg_quadrants_and_tail():
    pts = rotation.rrg(sector_prices())
    assert pts["Technology"]["quadrant"] == "leading" and pts["Utilities"]["quadrant"] == "lagging"
    assert len(pts["Technology"]["ratio"]) == rotation.TAIL and pts["Technology"]["dates"][-1] == "2026-10-12"
    assert pts["Energy"]["ratio"][-1] == pytest.approx(100.0)
    assert rotation.rrg(pd.DataFrame()) == {}


def test_relative_returns_and_portfolio_quadrants():
    rel = rotation.relative_returns(sector_prices())
    assert rel["Energy"][13] == pytest.approx(0.0, abs=1e-9)
    assert rel["Technology"][52] > 0 > rel["Utilities"][52]
    pts = rotation.rrg(sector_prices())
    by_q = rotation.portfolio_by_quadrant({"Technology": 30.0, "Utilities": 10.0, "Unknown": 5.0}, pts)
    assert by_q["leading"] == 30.0 and by_q["lagging"] == 10.0 and by_q["other"] == 5.0


def factor_world(seed=1):
    rng = np.random.default_rng(seed)
    rets = {"SPY": rng.normal(0.002, 0.02, 104)}
    for f, etf in factors.FACTORS.items():
        rets[etf] = rets["SPY"] + rng.normal(0, 0.01, 104)
    prices = pd.DataFrame({k: 100 * np.cumprod(1 + v) for k, v in rets.items()}, index=WEEKS)
    return rets, prices


def test_regression_recovers_known_tilts():
    rets, prices = factor_world()
    r = prices.pct_change()
    port = (0.9 * r["SPY"] + 0.4 * (r["MTUM"] - r["SPY"]) - 0.3 * (r["SCHD"] - r["SPY"])).iloc[1:]
    res = factors.regress(port, prices)
    assert res["beta"] == pytest.approx(0.9, abs=1e-6) and res["r2"] == pytest.approx(1.0)
    assert res["tilts"]["momentum"][0] == pytest.approx(0.4, abs=1e-6)
    assert res["tilts"]["dividend"][0] == pytest.approx(-0.3, abs=1e-6)
    assert res["tilts"]["value"][0] == pytest.approx(0.0, abs=1e-6)
    assert res["n"] == 103
    assert factors.regress(port.head(30), prices) is None


def test_portfolio_returns_weights_and_coverage():
    _, prices = factor_world()
    prices["THIN"] = np.nan
    prices.loc[prices.index[-10:], "THIN"] = 5.0
    port, cov = factors.portfolio_returns(prices, {"SPY": 75.0, "MTUM": 25.0, "THIN": 100.0, "MISSING": 0})
    r = prices.pct_change()
    assert cov == pytest.approx(50.0)
    assert port.iloc[-1] == pytest.approx(0.75 * r["SPY"].iloc[-1] + 0.25 * r["MTUM"].iloc[-1])
    assert factors.portfolio_returns(prices, {})[1] == 0.0


def _view_page():
    import pandas as pd
    import streamlit as st
    from exposure_ui import render_exposure_tab
    render_exposure_tab(pd.DataFrame([
        {"ticker": "AAA", "yahoo_symbol": "SPY", "value_disp": 60.0, "currencyCode": "USD"},
        {"ticker": "BBB", "yahoo_symbol": "MTUM", "value_disp": 40.0, "currencyCode": "USD"}]), "EUR")


@pytest.mark.parametrize("view, needle", [("rotation", "Lider"), ("factors", "Beta față de piață")])
def test_exposure_views_render(monkeypatch, tmp_path, view, needle):
    from streamlit.testing.v1 import AppTest
    import compare_ui
    import exposure
    _, fprices = factor_world()
    world = pd.concat([sector_prices(), fprices.drop(columns=["SPY"])], axis=1)
    monkeypatch.setattr(compare_ui, "get_closes", lambda symbols, period, interval: world[[s for s in symbols if s in world]])
    monkeypatch.setattr(exposure, "EXPOSURE_CACHE_FILE", str(tmp_path / "ex.json"))
    monkeypatch.setattr(exposure, "EXPOSURE_STATUS_FILE", str(tmp_path / "exs.json"))
    at = AppTest.from_function(_view_page)
    at.session_state["ex_view"] = view  # AppTest nu citeste bind="query-params" din URL
    at.run(timeout=20)
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert needle in labels
