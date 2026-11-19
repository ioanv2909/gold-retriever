"""Proiectia pensiei: puncte, stabilitate, anticipata, impozitare, piloni, valoarea ca avere."""
from datetime import date

import pytest

import pension

BASE = {"points": 20.0, "contrib_years": 20.0, "points_per_year": 1.0, "birth_year": 1980, "birth_month": 1,
        "retire_age": 65, "full_stage": 35, "vpr": 81.0, "payout_years": 18, "real_return": 0.0}


def test_stability_points():
    assert pension.stability_points(25) == 0
    assert pension.stability_points(30) == pytest.approx(2.5)
    assert pension.stability_points(33) == pytest.approx(4.75)
    assert pension.stability_points(35) == pytest.approx(6.25)
    assert pension.stability_points(40) == pytest.approx(11.25)


def test_net_pension():
    assert pension.net_pension(2500)["net"] == pytest.approx(2500)
    r = pension.net_pension(4000)
    assert (r["cass"], r["tax"], r["net"]) == (pytest.approx(100), pytest.approx(90), pytest.approx(3810))


def test_early_rate_table():
    assert [pension.early_rate(x) for x in (0, 0.9, 1, 2.5, 3.2, 4, 8)] == [0.40, 0.40, 0.35, 0.30, 0.25, 0.20, 0.20]


def test_projection_at_standard_age():
    r = pension.project(BASE, today=date(2025, 1, 1))
    assert r["years_left"] == pytest.approx(20)
    assert r["contrib_years_at_retire"] == pytest.approx(40)
    assert r["points_at_retire"] == pytest.approx(20 + 20 + 11.25)
    assert r["gross_at_retire"] == pytest.approx(51.25 * 81)
    assert r["pension_at_retire"] == pytest.approx(pension.net_pension(51.25 * 81)["net"])
    assert r["wealth_at_retire"] == pytest.approx(r["pension_at_retire"] * 216)
    assert r["standard_date"] == (2045, 1) and r["out_date"] == (2045, 1)
    assert r["penalty"] == 0
    # full stage (35) is reached at 60 = exactly 5 years early
    assert r["early_possible"] and r["earliest_age"] == pytest.approx(60) and r["earliest_date"] == (2040, 1)


def test_early_retirement_penalty():
    r = pension.project(dict(BASE, planned_age=62), today=date(2025, 1, 1))
    assert r["planned_ok"] and r["months_early"] == 36
    # at 62: 37 contribution years = 2 years over the full period -> 0.30% a month
    assert r["early_rate"] == pytest.approx(0.30) and r["penalty"] == pytest.approx(0.108)
    pts = 20 + 17 + pension.stability_points(37) - pension.stability_points(20)
    assert r["gross_at_retire"] == pytest.approx(pts * 81 * (1 - 0.108))


def test_too_early_falls_back_to_standard_age():
    r = pension.project(dict(BASE, planned_age=58), today=date(2025, 1, 1))
    assert not r["planned_ok"] and r["age_out"] == 65 and r["penalty"] == 0


def test_no_early_without_full_stage():
    r = pension.project(dict(BASE, contrib_years=10), today=date(2025, 1, 1))
    assert not r["early_possible"] and r["full_stage_reached_age"] == pytest.approx(70)


def test_stability_already_earned_is_not_counted_twice():
    cfg = {"points": 40.0, "contrib_years": 32.0, "points_per_year": 0.0, "birth_year": 1965, "birth_month": 6,
           "retire_age": 65, "vpr": 81.0}
    r = pension.project(cfg, today=date(2025, 6, 1))
    assert r["extra_stability"] == pytest.approx(pension.stability_points(37) - pension.stability_points(32))


def test_private_pillars_future_value():
    assert pension.future_value(1000, 0, 0, 120) == pytest.approx(1000)
    assert pension.future_value(0, 100, 0, 12) == pytest.approx(1200)
    assert pension.future_value(1000, 0, 10, 12) == pytest.approx(1100)


def test_clean_limits_currency_and_save_roundtrip():
    cfg = pension.clean({"points": -5, "vpr": "abc", "retire_age": 99, "unknown": 1, "currency": "GBP"})
    assert cfg["points"] == 0 and cfg["vpr"] == pension.DEFAULTS["vpr"] and cfg["retire_age"] == 75
    assert "unknown" not in cfg and cfg["currency"] == "RON"
    pension.save({"points": 25.5, "contrib_years": 18, "currency": "EUR"})
    assert pension.load()["points"] == pytest.approx(25.5) and pension.load()["currency"] == "EUR"


def test_timeline_matches_the_chosen_age():
    r = pension.project(dict(BASE, planned_age=62), today=date(2025, 1, 1))
    row = next(x for x in r["timeline"] if x["chosen"])
    assert row["age"] == 62 and row["gross"] == pytest.approx(r["gross_at_retire"]) and row["net"] == pytest.approx(r["pension_at_retire"])
    std = next(x for x in r["timeline"] if x["age"] == 65)
    assert std["penalty"] == 0 and std["allowed"]
    assert any(x["age"] == 60 for x in r["timeline"])  # earliest early-retirement age is listed
    assert not next(x for x in r["timeline"] if x["age"] == 55)["allowed"]
