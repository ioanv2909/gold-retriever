"""Tabul Pensie: datele pentru proiectie (per utilizator) si rezultatul, in bani de azi, brut si net."""
import pandas as pd
import streamlit as st

import notice
import pension
from i18n import t
from portfolio_model import fx
from privacy import mask

_SYMBOL = {"RON": "lei", "EUR": "EUR", "USD": "USD"}


def _money(v, ccy, rate):
    return mask(f"{v * rate:,.0f} {_SYMBOL[ccy]}".replace(",", "."))


def _ym(pair):
    year, month = pair
    return f"{month:02d}.{year}"


def _form(cfg):
    with st.form("pension_form"):
        st.markdown(f"**{t('pen.sec_state')}**")
        c1, c2, c3 = st.columns(3)
        points = c1.number_input(t("pen.points"), 0.0, 200.0, cfg["points"], 0.01, format="%.5f", help=t("pen.points_help"))
        contrib = c2.number_input(t("pen.contrib_years"), 0.0, 60.0, cfg["contrib_years"], 0.5, help=t("pen.contrib_help"))
        ppy = c3.number_input(t("pen.ppy"), 0.0, 10.0, cfg["points_per_year"], 0.05, help=t("pen.ppy_help"))
        c1, c2, c3, c4 = st.columns(4)
        by = c1.number_input(t("pen.birth_year"), 1930, 2015, cfg["birth_year"], 1)
        bm = c2.number_input(t("pen.birth_month"), 1, 12, cfg["birth_month"], 1)
        ra = c3.number_input(t("pen.retire_age"), 40.0, 75.0, cfg["retire_age"], 0.25, help=t("pen.retire_help"))
        fs = c4.number_input(t("pen.full_stage"), 10.0, 45.0, cfg["full_stage"], 0.5, help=t("pen.full_stage_help"))
        c1, c2, c3, c4 = st.columns(4)
        pa = c1.number_input(t("pen.planned_age"), 0.0, 75.0, cfg["planned_age"], 0.25, help=t("pen.planned_help"))
        vpr = c2.number_input(t("pen.vpr"), 0.0, 100000.0, cfg["vpr"], 0.5, help=t("pen.vpr_help"))
        payout = c3.number_input(t("pen.payout_years"), 1.0, 50.0, cfg["payout_years"], 1.0, help=t("pen.payout_help"))
        rr = c4.number_input(t("pen.real_return"), -5.0, 15.0, cfg["real_return"], 0.25, help=t("pen.real_return_help"))
        st.markdown(f"**{t('pen.sec_private')}**")
        c1, c2, c3 = st.columns(3)
        p2b = c1.number_input(t("pen.p2_balance"), 0.0, 1e9, cfg["p2_balance"], 100.0, help=t("pen.p2_help"))
        p2m = c2.number_input(t("pen.p2_monthly"), 0.0, 1e7, cfg["p2_monthly"], 10.0, help=t("pen.p2m_help"))
        p2r = c3.number_input(t("pen.p2_return"), -5.0, 15.0, cfg["p2_return"], 0.25)
        c1, c2, c3 = st.columns(3)
        p3b = c1.number_input(t("pen.p3_balance"), 0.0, 1e9, cfg["p3_balance"], 100.0)
        p3m = c2.number_input(t("pen.p3_monthly"), 0.0, 1e7, cfg["p3_monthly"], 10.0)
        p3r = c3.number_input(t("pen.p3_return"), -5.0, 15.0, cfg["p3_return"], 0.25)
        if st.form_submit_button(t("pen.save"), type="primary"):
            cfg = pension.save({"points": points, "contrib_years": contrib, "points_per_year": ppy, "birth_year": by,
                                "birth_month": bm, "retire_age": ra, "full_stage": fs, "planned_age": pa, "vpr": vpr,
                                "payout_years": payout, "real_return": rr, "p2_balance": p2b, "p2_monthly": p2m,
                                "p2_return": p2r, "p3_balance": p3b, "p3_monthly": p3m, "p3_return": p3r,
                                "currency": cfg["currency"], "p2_upfront": cfg["p2_upfront"], "p2_years": cfg["p2_years"]})
            st.success(t("pen.saved"))
    return cfg


def _when(r):
    lines = [t("pen.when_standard", age=f"{r['standard_age']:g}", date=_ym(r["standard_date"]))]
    if r["early_possible"]:
        lines.append(t("pen.when_early", age=f"{r['earliest_age']:.1f}", date=_ym(r["earliest_date"])))
    else:
        lines.append(t("pen.when_no_early", age=f"{r['full_stage_reached_age']:.1f}"))
    if not r["planned_ok"]:
        lines.append(t("pen.when_planned_bad", age=f"{r['planned_age']:g}"))
    elif r["months_early"]:
        lines.append(t("pen.when_penalty", months=r["months_early"], rate=f"{r['early_rate']:.2f}",
                       pct=f"{r['penalty'] * 100:.1f}", surplus=f"{max(0, r['surplus_years']):.1f}"))
    elif r["age_out"] > r["standard_age"]:
        lines.append(t("pen.when_later", age=f"{r['age_out']:g}"))
    return lines


def _go(**params):
    """Deschide alta pagina/alt tab prin parametrii din URL (Setari: ?page=settings&tab=pension)."""
    st.query_params.clear()
    st.query_params.update(params)
    st.rerun()


def render_pension_settings():
    """Setari -> Pensii: datele pentru proiectie (rezultatele sunt in tabul Pensie de pe pagina principala)."""
    st.caption(t("pen.intro"))
    cfg = _form(pension.load())
    if cfg["points"] or cfg["contrib_years"]:
        if st.button(t("pen.open_results"), key="pension_open_results"):
            _go(page="pension")


def render_pension_tab():
    """Tabul Pensie de pe pagina principala: doar rezultatele; datele se completeaza in Setari -> Pensii."""
    cfg = pension.load()
    if not cfg["points"] and not cfg["contrib_years"]:
        notice.card(t("pen.empty"), icon="ℹ️")
        if st.button(t("pen.open_settings"), key="pension_open_settings_empty", type="primary"):
            _go(page="settings", tab="pension")
        return
    if st.button(t("pen.open_settings"), key="pension_open_settings"):
        _go(page="settings", tab="pension")
    ccy = st.radio(t("pen.currency"), pension.CURRENCIES, index=pension.CURRENCIES.index(cfg["currency"]),
                   horizontal=True, key="pension_ccy")
    if ccy != cfg["currency"]:
        cfg = pension.save(dict(cfg, currency=ccy))
    rate = fx("RON", ccy) if ccy != "RON" else 1.0
    if ccy != "RON":
        st.caption(t("pen.rate", ccy=ccy, rate=f"{1 / rate:.4f}" if rate else "?"))

    r = pension.project(cfg)
    tab1, tab2, tab3 = st.tabs([t("pen.tab_p1"), t("pen.tab_p2"), t("pen.tab_p3")])
    with tab1:
        _scenarios(cfg, ccy, rate)
        _pillar1(r, ccy, rate)
    with tab2:
        _private(cfg, r, "p2", ccy, rate)
    with tab3:
        _private(cfg, r, "p3", ccy, rate)


def _private(cfg, r, key, ccy, rate):
    """Pilonul II / III: soldul de azi si valoarea estimata la pensionare (bani reali, nu estimari de venit)."""
    balance, monthly, ret = cfg[key + "_balance"], cfg[key + "_monthly"], cfg[key + "_return"]
    if not balance and not monthly:
        notice.card(t("pen.private_empty"), icon="ℹ️")
        return
    at_retire = r[key + "_at_retire"]
    paid_in = balance + monthly * r["months_left"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("pen.m_balance_now"), _money(balance, ccy, rate))
    c2.metric(t("pen.m_monthly"), _money(monthly, ccy, rate))
    c3.metric(t("pen.m_return"), f"{ret:g}%")
    c4.metric(t("pen.m_at_retire"), _money(at_retire, ccy, rate),
              help=t("pen.m_at_retire_help", date=_ym(r["out_date"]), gain=_money(at_retire - paid_in, ccy, rate)))
    st.markdown(f"**{t('pen.pv_title')}**")
    if key == "p2":
        c1, c2 = st.columns(2)
        up = c1.slider(t("pen.p2_upfront"), 0, 30, int(cfg["p2_upfront"]), 5, format="%d%%", help=t("pen.p2_upfront_help"),
                       key="p2_upfront")
        yrs = c2.slider(t("pen.p2_years"), 8, 40, int(cfg["p2_years"]), 1, help=t("pen.p2_years_help"), key="p2_years")
        if up != cfg["p2_upfront"] or yrs != cfg["p2_years"]:
            cfg = pension.save(dict(cfg, p2_upfront=up, p2_years=yrs))
    chosen = cfg["planned_age"] or cfg["retire_age"]
    out = []
    for x in pension.private_by_age(cfg, key):
        row = {t("pen.col_age"): (f"▶ {x['age']:g}" if abs(x["age"] - chosen) < 1e-9 else f"{x['age']:g}"),
               t("pen.col_year"): _ym(x["date"]),
               t("pen.pv_col_paid"): _money(x["paid_in"], ccy, rate),
               t("pen.pv_col_value"): _money(x["value"], ccy, rate),
               t("pen.pv_col_gain"): _money(x["gain"], ccy, rate)}
        if key == "p2":
            lump, monthly_pay = pension.p2_payout(x["value"], cfg["p2_upfront"], cfg["p2_years"])
            row[t("pen.pv_col_lump", pct=f"{cfg['p2_upfront']:g}")] = _money(lump, ccy, rate)
            row[t("pen.pv_col_rate", years=f"{cfg['p2_years']:g}")] = _money(monthly_pay, ccy, rate)
        else:
            row[t("pen.pv_col_month")] = _money(x["value"] / (cfg["payout_years"] * 12), ccy, rate)
        out.append(row)
    st.dataframe(pd.DataFrame(out), hide_index=True, width="content")
    st.caption(t("pen.pv_note_" + key, years=f"{cfg['payout_years']:g}"))


def _scenarios(cfg, ccy, rate):
    """Scenariile: punctele de pana azi si continuarea cu acelasi salariu pana la 55 / 60 / 65 de ani."""
    rows = pension.scenarios(cfg)
    st.subheader(t("pen.sc_title"))
    st.caption(t("pen.sc_intro", ppy=f"{cfg['points_per_year']:g}"))
    out = []
    for x in rows:
        early = x["earliest_age"] < x["std_age"] - 1e-9
        out.append({
            t("pen.sc_col_stop"): t("pen.sc_now") if x["stop_age"] is None else t("pen.sc_until", age=f"{x['stop_age']:g}"),
            t("pen.sc_col_contrib"): f"{x['contrib_years']:.1f}",
            t("pen.sc_col_points"): f"{x['points']:.2f}",
            t("pen.sc_col_earliest"): (f"{x['earliest_age']:.1f} ({_ym(x['earliest_date'])})" if early else "—"),
            t("pen.sc_col_net_early"): (f"{_money(x['net_earliest'], ccy, rate)} (−{x['penalty'] * 100:.0f}%)" if early else "—"),
            t("pen.sc_col_std"): f"{x['std_age']:g} ({_ym(x['std_date'])})",
            t("pen.sc_col_net_std"): _money(x["net_std"], ccy, rate),
        })
    st.dataframe(pd.DataFrame(out), hide_index=True, width="content")
    first = rows[0]
    if not first["full_stage"]:
        st.caption(t("pen.sc_note_full", years=f"{cfg['full_stage']:g}"))


def _pillar1(r, ccy, rate):
    st.subheader(t("pen.when_title"))
    for line in _when(r):
        st.markdown("- " + line)

    st.subheader(t("pen.result_title", date=_ym(r["out_date"]), age=f"{r['age_out']:g}"))
    tx = r["tax_at_retire"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("pen.m_years_left"), f"{r['years_left']:.1f}")
    c2.metric(t("pen.m_points"), f"{r['points_at_retire']:.2f}", help=t("pen.m_points_help", extra=f"{r['extra_stability']:.2f}"))
    c3.metric(t("pen.m_gross"), _money(tx["gross"], ccy, rate), help=t("pen.m_gross_help"))
    c4.metric(t("pen.m_net"), _money(tx["net"], ccy, rate),
              help=t("pen.m_net_help", cass=_money(tx["cass"], ccy, rate), tax=_money(tx["tax"], ccy, rate)))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("pen.m_pension_now"), _money(r["pension_now"], ccy, rate), help=t("pen.m_pension_now_help"))
    c2.metric(t("pen.m_wealth_retire"), _money(r["wealth_at_retire"], ccy, rate), help=t("pen.m_wealth_retire_help"))
    c3.metric(t("pen.m_wealth_today"), _money(r["wealth_today"], ccy, rate), help=t("pen.m_wealth_today_help"))
    if r["timeline"]:
        st.markdown(f"**{t('pen.timeline')}**")
        no = t("pen.not_allowed")
        df = pd.DataFrame([{t("pen.col_age"): (f"▶ {x['age']:g}" if x["chosen"] else f"{x['age']:g}"),
                            t("pen.col_year"): _ym(x["date"]),
                            t("pen.col_points"): round(x["points"], 2),
                            t("pen.col_penalty"): (no if not x["allowed"] else (f"−{x['penalty'] * 100:.1f}%" if x["penalty"] else "—")),
                            t("pen.col_gross"): _money(x["gross"], ccy, rate) if x["allowed"] else no,
                            t("pen.col_net"): _money(x["net"], ccy, rate) if x["allowed"] else no} for x in r["timeline"]])
        st.dataframe(df, hide_index=True, width="content")
    notice.card(t("pen.assumptions"), icon="ℹ️")
