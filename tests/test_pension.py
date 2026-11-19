"""Proiectia pensiei: puncte, stabilitate, piloni, valoarea ca avere."""
from datetime import date

import pytest

import pension


def test_stability_points():
    assert pension.stability_points(25) == 0
    assert pension.stability_points(30) == pytest.approx(2.5)
    assert pension.stability_points(35) == pytest.approx(6.25)
    assert pension.stability_points(40) == pytest.approx(11.25)


def test_projection_points_and_pension():
    cfg = {"points": 20.0, "contrib_years": 20.0, "points_per_year": 1.0, "birth_year": 1980, "birth_month": 1,
           "retire_age": 65, "vpr": 81.0, "payout_years": 18, "real_return": 0.0}
    r = pension.project(cfg, today=date(2025, 1, 1))
    assert r["years_left"] == pytest.approx(20)
    assert r["contrib_years_at_retire"] == pytest.approx(40)
    assert r["extra_stability"] == pytest.approx(11.25)
    assert r["points_at_retire"] == pytest.approx(20 + 20 + 11.25)
    assert r["pension_at_retire"] == pytest.approx(51.25 * 81)
    assert r["pension_now"] == pytest.approx(20 * 81)
    # randament 0: averea = pensia × numarul de luni
    assert r["wealth_at_retire"] == pytest.approx(51.25 * 81 * 216)
    assert r["wealth_today"] == pytest.approx(r["wealth_at_retire"])
    assert r["retire_year"] == 2045
    assert r["timeline"][-1]["age"] == 65


def test_stability_already_earned_is_not_counted_twice():
    cfg = {"points": 40.0, "contrib_years": 32.0, "points_per_year": 0.0, "birth_year": 1965, "birth_month": 6,
           "retire_age": 65, "vpr": 81.0}
    r = pension.project(cfg, today=date(2025, 6, 1))
    assert r["extra_stability"] == pytest.approx(pension.stability_points(37) - pension.stability_points(32))


def test_after_retirement_age_nothing_is_added():
    r = pension.project({"points": 30, "contrib_years": 40, "birth_year": 1950, "retire_age": 65}, today=date(2025, 1, 1))
    assert r["years_left"] == 0 and r["points_at_retire"] == pytest.approx(30)


def test_private_pillars_future_value():
    assert pension.future_value(1000, 0, 0, 120) == pytest.approx(1000)
    assert pension.future_value(0, 100, 0, 12) == pytest.approx(1200)
    assert pension.future_value(1000, 0, 10, 12) == pytest.approx(1100)


def test_clean_limits_and_save_roundtrip():
    cfg = pension.clean({"points": -5, "vpr": "abc", "retire_age": 99, "unknown": 1})
    assert cfg["points"] == 0 and cfg["vpr"] == pension.DEFAULTS["vpr"] and cfg["retire_age"] == 75
    assert "unknown" not in cfg
    pension.save({"points": 25.5, "contrib_years": 18})
    assert pension.load()["points"] == pytest.approx(25.5)
