"""Tabul Pensie: datele pentru proiectie (per utilizator) si rezultatul, in bani de azi."""
import pandas as pd
import streamlit as st

import notice
import pension
from i18n import t
from privacy import mask


def _lei(v):
    return mask(f"{v:,.0f} lei".replace(",", "."))


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
        vpr = c4.number_input(t("pen.vpr"), 0.0, 100000.0, cfg["vpr"], 0.5, help=t("pen.vpr_help"))
        c1, c2 = st.columns(2)
        payout = c1.number_input(t("pen.payout_years"), 1.0, 50.0, cfg["payout_years"], 1.0, help=t("pen.payout_help"))
        rr = c2.number_input(t("pen.real_return"), -5.0, 15.0, cfg["real_return"], 0.25, help=t("pen.real_return_help"))
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
                                "birth_month": bm, "retire_age": ra, "vpr": vpr, "payout_years": payout,
                                "real_return": rr, "p2_balance": p2b, "p2_monthly": p2m, "p2_return": p2r,
                                "p3_balance": p3b, "p3_monthly": p3m, "p3_return": p3r})
            st.success(t("pen.saved"))
    return cfg


def render_pension_tab():
    st.caption(t("pen.intro"))
    cfg = _form(pension.load())
    if not cfg["points"] and not cfg["contrib_years"]:
        notice.card(t("pen.empty"), icon="ℹ️")
        return
    r = pension.project(cfg)
    st.subheader(t("pen.result_title", year=r["retire_year"], age=f"{cfg['retire_age']:g}"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("pen.m_years_left"), f"{r['years_left']:.1f}")
    c2.metric(t("pen.m_points"), f"{r['points_at_retire']:.2f}", help=t("pen.m_points_help", extra=f"{r['extra_stability']:.2f}"))
    c3.metric(t("pen.m_pension"), _lei(r["pension_at_retire"]), help=t("pen.m_pension_help"))
    c4.metric(t("pen.m_pension_now"), _lei(r["pension_now"]), help=t("pen.m_pension_now_help"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("pen.m_wealth_retire"), _lei(r["wealth_at_retire"]), help=t("pen.m_wealth_retire_help"))
    c2.metric(t("pen.m_wealth_today"), _lei(r["wealth_today"]), help=t("pen.m_wealth_today_help"))
    c3.metric(t("pen.m_p2"), _lei(r["p2_at_retire"]))
    c4.metric(t("pen.m_p3"), _lei(r["p3_at_retire"]))
    total = r["wealth_at_retire"] + r["p2_at_retire"] + r["p3_at_retire"]
    st.markdown(t("pen.total", total=_lei(total)))
    if r["timeline"]:
        st.markdown(f"**{t('pen.timeline')}**")
        df = pd.DataFrame([{t("pen.col_age"): x["age"], t("pen.col_year"): x["year"],
                            t("pen.col_points"): round(x["points"], 2), t("pen.col_pension"): _lei(x["pension"])}
                           for x in r["timeline"]])
        st.dataframe(df, hide_index=True, width="content")
    notice.card(t("pen.assumptions"), icon="ℹ️")
