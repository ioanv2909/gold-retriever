import pandas as pd

import chart_window as cw


def test_view_start_periods():
    idx = pd.date_range("2025-01-01", "2026-11-06", freq="D")
    assert cw.view_start(idx, "1mo") == pd.Timestamp("2026-10-06")
    assert cw.view_start(idx, "1y") == pd.Timestamp("2025-11-06")
    assert cw.view_start(idx, "ytd") == pd.Timestamp("2026-01-01")
    assert cw.view_start(idx, "max") is None


def test_view_start_trading_days_intraday():
    idx = pd.DatetimeIndex(["2026-11-04 15:30", "2026-11-04 16:00", "2026-11-05 15:30",
                            "2026-11-06 15:30", "2026-11-06 16:00"], tz="America/New_York")
    assert cw.view_start(idx, "1d") == idx[3]
    assert cw.view_start(idx, "5d") == idx[0]


def test_padded_range():
    assert cw.padded_range([10.0, 20.0, None]) == [9.5, 20.5]
    assert cw.padded_range([]) is None


def test_every_chart_period_has_a_load_period():
    from core import CHART_PERIODS
    assert set(CHART_PERIODS) <= set(cw.CHART_LOAD)
