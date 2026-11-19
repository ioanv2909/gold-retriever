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


def test_settings_has_the_pension_form_and_the_tab_only_results():
    import inspect
    import pension_ui
    import settings_page
    assert "render_pension_settings" in inspect.getsource(settings_page)
    tab_src = inspect.getsource(pension_ui.render_pension_tab)
    assert "_form(" not in tab_src and "pension.load()" in tab_src
    assert "_form(" in inspect.getsource(pension_ui.render_pension_settings)


def test_pension_is_a_top_section_not_a_portfolio_tab():
    import inspect
    import main_view
    tabs_src = inspect.getsource(main_view._render_tabs)
    assert "pension" not in tabs_src
    assert main_view.TOP_SECTIONS == ("summary", "portfolio", "pension")
    assert "segmented_control" in inspect.getsource(main_view._top_section)


def test_pension_page_has_a_tab_per_pillar():
    import inspect
    import pension_ui
    src = inspect.getsource(pension_ui.render_pension_tab)
    assert "pen.tab_p1" in src and "pen.tab_p2" in src and "pen.tab_p3" in src
    assert "pen.total" not in inspect.getsource(pension_ui)  # pensia de stat nu se aduna cu banii reali


def test_scenarios_stop_now_and_keep_working():
    cfg = dict(BASE, points=80.0, contrib_years=24.0, points_per_year=3.0, birth_year=1979, birth_month=3)
    rows = pension.scenarios(cfg, today=date(2026, 11, 1))
    now, at55, at60, at65 = rows
    # stop now: 24 years < 35 -> no early retirement, pension at 65 with today's points
    assert now["stop_age"] is None and not now["full_stage"] and now["earliest_age"] == pytest.approx(65)
    assert now["net_std"] == pytest.approx(pension.net_pension(80.0 * 81)["net"])
    # until 55: ~32 years < 35 -> still only at 65
    assert at55["stop_age"] == 55 and not at55["full_stage"] and at55["earliest_age"] == pytest.approx(65)
    # until 60: ~37 years >= 35 -> can start at 60 with a reduction
    assert at60["full_stage"] and at60["earliest_age"] == pytest.approx(60) and at60["penalty"] > 0
    assert at60["net_earliest"] < at60["net_std"]
    assert at65["penalty"] == 0 and at65["net_std"] > at60["net_std"]


def test_private_pillar_values_by_age():
    cfg = dict(BASE, p2_balance=1000, p2_monthly=100, p2_return=0, planned_age=62)
    rows = pension.private_by_age(cfg, "p2", today=date(2025, 1, 1))
    ages = [x["age"] for x in rows]
    assert ages == sorted(ages) and 62 in ages and 65 in ages and all(a > 45 for a in ages)
    at60 = next(x for x in rows if x["age"] == 60)
    assert at60["months"] == 180 and at60["value"] == pytest.approx(1000 + 100 * 180) and at60["gain"] == pytest.approx(0)
    p3 = pension.private_by_age(dict(cfg, p3_balance=500), "p3", today=date(2025, 1, 1))
    assert not next(x for x in p3 if x["age"] == 55)["available"] and next(x for x in p3 if x["age"] == 60)["available"]


def test_pillar2_payout_law_limits():
    lump, monthly = pension.p2_payout(100000, 30, 8)
    assert lump == pytest.approx(30000) and monthly == pytest.approx(100000 * 0.7 / 96)
    assert pension.p2_payout(1000, 50, 2) == pension.p2_payout(1000, 30, 8)  # max 30%, min 8 ani
    cfg = pension.clean({"p2_upfront": 45, "p2_years": 3})
    assert cfg["p2_upfront"] == 30 and cfg["p2_years"] == 8


def test_settings_form_keeps_the_payout_choice():
    import inspect
    import pension_ui
    src = inspect.getsource(pension_ui._form)
    assert "p2_upfront" in src and "p2_years" in src


def test_totals_by_age_combine_the_pillars():
    cfg = dict(BASE, p2_balance=100000, p2_monthly=0, p2_return=0, p3_balance=12000, p3_monthly=0, p3_return=0,
               payout_years=10, p2_upfront=30, p2_years=8)
    rows = {x["age"]: x for x in pension.totals_by_age(cfg, today=date(2025, 1, 1))}
    assert not rows[55]["allowed"] and rows[55]["monthly"] is None          # prea devreme pentru pensie
    r65 = rows[65]
    assert r65["state"] == pytest.approx(pension.project(cfg, today=date(2025, 1, 1))["pension_at_retire"])
    assert r65["p2_lump"] == pytest.approx(30000) and r65["p2_month"] == pytest.approx(70000 / 96)
    assert r65["p3_month"] == pytest.approx(100)
    assert r65["monthly"] == pytest.approx(r65["state"] + r65["p2_month"] + 100)
    assert r65["after_p2"] == pytest.approx(r65["state"] + 100)
    assert rows[60]["allowed"] and rows[60]["penalty"] > 0
