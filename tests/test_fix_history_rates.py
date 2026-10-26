import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "fix_history_rates", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "fix_history_rates.py"))
fhr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fhr)


def _p(ts, ron_value, ron_rate, eur_value=1000.0):
    return {"ts": ts, "entries": {"XTB": {"ccy": "RON", "value": ron_value}, "Trading 212": {"ccy": "EUR", "value": eur_value}},
            "rates": {"EUR": 1.0, "RON": ron_rate, "USD": 0.9}}


def test_made_up_rate_points_are_marked():
    h = [_p("2026-10-%02dT10:00:00" % d, 5000.0, 0.2) for d in range(1, 10)] + [_p("2026-10-26T10:00:00", 5000.0, 1.0)]
    bad, ratios = fhr.analyse(h, 0)
    assert [i for i, _, _ in bad] == [9]
    assert ratios[9] > 2.5  # 5000 RON luati drept euro


def test_ratio_filter_is_optional():
    h = [_p("2026-10-%02dT10:00:00" % d, 5000.0, 0.2) for d in range(1, 10)] + [_p("2026-10-26T10:00:00", 50000.0, 0.2)]
    assert fhr.analyse(h, 0)[0] == []
    assert [i for i, _, _ in fhr.analyse(h, 2)[0]] == [9]


def test_normal_history_is_untouched():
    h = [_p("2026-10-%02dT10:00:00" % d, 5000.0 + d * 10, 0.2) for d in range(1, 20)]
    assert fhr.analyse(h, 2)[0] == []
