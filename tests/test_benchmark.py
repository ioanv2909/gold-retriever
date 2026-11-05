import pandas as pd

import benchmark


def test_simulate_tracks_index_and_flows():
    # porneste de la 1000, indicele creste 10%, apoi se mai investesc 500 la pretul nou
    out = benchmark.simulate([1000, 1100, 1650], [1000, 1000, 1500], [100, 110, 110])
    assert [round(v, 6) for v in out] == [1000, 1100, 1600]


def test_simulate_withdrawal_and_bad_price():
    out = benchmark.simulate([1000, 500], [1000, 500], [100, 100])
    assert round(out[1], 6) == 500
    assert benchmark.simulate([1000, 900], [1000, 1000], [100, float("nan")]) is None


def test_align_uses_last_known_price():
    px = pd.Series([10.0, 20.0], index=pd.to_datetime(["2026-01-02", "2026-01-05"]))
    x = pd.to_datetime(["2026-01-01", "2026-01-03", "2026-01-06"])
    assert benchmark.align(x, px).tolist() == [10.0, 10.0, 20.0]


def test_ranges_cover_history_ranges():
    from history_ui import HIST_RANGES
    assert set(HIST_RANGES) <= set(benchmark.YF_RANGE)
