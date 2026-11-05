from core import CHART_PERIODS, HIST_TO_CHART
from history_ui import HIST_RANGES, HIST_RANGES_COMPACT, _HIST_NEAR_COMPACT
from i18n import _T


def test_new_periods_present():
    for k in ("3L", "6L", "3A", "5A"):
        assert k in CHART_PERIODS
    for k in ("3M", "6M", "3Y", "5Y"):
        assert k in HIST_RANGES


def test_history_ranges_map_to_chart_periods():
    assert set(HIST_TO_CHART) == set(HIST_RANGES)
    assert all(v in CHART_PERIODS for v in HIST_TO_CHART.values())


def test_compact_near_targets_exist():
    assert set(HIST_RANGES) == set(HIST_RANGES_COMPACT) | set(_HIST_NEAR_COMPACT)
    assert all(v in HIST_RANGES_COMPACT for v in _HIST_NEAR_COMPACT.values())


def test_chart_period_labels_translated():
    for k in CHART_PERIODS:
        assert {"RO", "EN"} <= set(_T["dv.per." + k])
