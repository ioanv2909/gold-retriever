"""Sectiunea Rezumat: investitiile si pensiile intr-un singur loc (fiecare cu ce reprezinta)."""
import streamlit as st

import notice
import pension
from i18n import t
from portfolio_model import build_rows, fx, portfolio_options
from privacy import mask

_SYMBOL = {"RON": "lei", "EUR": "EUR", "USD": "USD"}


def _money(v, ccy):
    return mask(f"{v:,.0f} {_SYMBOL.get(ccy, ccy)}".replace(",", "."))


def history(opts, ccy):
    """(depuneri nete, luni, ritm lunar) din jurnalul operatiunilor, pentru portofoliile date, in ccy."""
    import journal
    import pace_target
    ops = [op for op in journal.load_all({}) if op["type"] in ("deposit", "withdrawal", "buy")]
    _, net, months, pace = pace_target.pace_of(ops, ccy, set(opts))
    return net, months, pace


def _projection(cfg, inv, ccy):
    """Proiectia investitiilor la bursa: valoarea de azi + depunerea lunara, la randamentul ales."""
    cost, value, opts = inv
    st.subheader(t("sum.proj_title"))
    try:
        net, months, pace = history(opts, ccy)
    except Exception:
        net, months, pace = None, None, None
    cash = max(0.0, (net or 0) - cost)
    now_value = value + cash
    hist = pension.uniform_return(net, months, now_value) if net and months else None
    inv_rate = fx(cfg["inv_ccy"], ccy) if cfg["inv_ccy"] != ccy else 1.0
    with st.form("invest_projection"):
        c1, c2, c3, c4 = st.columns(4)
        m_ccy = c1.selectbox(t("sum.proj_ccy"), pension.CURRENCIES, index=pension.CURRENCIES.index(cfg["inv_ccy"]))
        default_m = cfg["inv_monthly"] or ((pace or 0) / (inv_rate or 1))
        monthly = c2.number_input(t("sum.proj_monthly"), 0.0, 1e7, float(round(default_m, 0)), 50.0,
                                  help=t("sum.proj_monthly_help", pace=_money(pace or 0, ccy)))
        default_r = cfg["inv_return"] if cfg["inv_return"] > -99 else round(hist if hist is not None else 6.0, 1)
        ret = c3.number_input(t("sum.proj_return"), -10.0, 30.0, float(default_r), 0.1,
                              help=t("sum.proj_return_help", hist=f"{hist:.1f}%" if hist is not None else "—"))
        infl = c4.number_input(t("sum.proj_inflation"), 0.0, 30.0, float(cfg["inv_inflation"]), 0.1)
        if st.form_submit_button(t("sum.proj_save")):
            cfg = pension.save(dict(cfg, inv_ccy=m_ccy, inv_monthly=monthly, inv_return=ret, inv_inflation=infl))
            inv_rate = fx(cfg["inv_ccy"], ccy) if cfg["inv_ccy"] != ccy else 1.0
    monthly_disp = (cfg["inv_monthly"] or ((pace or 0) / (inv_rate or 1))) * (inv_rate or 1)
    ret_used = cfg["inv_return"] if cfg["inv_return"] > -99 else (hist if hist is not None else 6.0)
    rows = pension.invest_by_age(cfg, now_value, monthly_disp, ret_used, cfg["inv_inflation"])
    chosen = cfg["planned_age"] or cfg["retire_age"]
    import pandas as pd
    out = [{t("pen.col_age"): (f"▶ {x['age']:g}" if abs(x["age"] - chosen) < 1e-9 else f"{x['age']:g}"),
            t("pen.col_year"): f"{x['date'][1]:02d}.{x['date'][0]}",
            t("sum.proj_col_paid"): _money(x["paid_in"], ccy),
            t("sum.proj_col_value"): _money(x["value"], ccy),
            t("sum.proj_col_gain"): _money(x["value"] - x["paid_in"], ccy),
            t("sum.proj_col_real"): _money(x["real"], ccy)} for x in rows]
    st.dataframe(pd.DataFrame(out), hide_index=True, width="content")
    st.caption(t("sum.proj_note", now=_money(now_value, ccy), monthly=_money(monthly_disp, ccy), ret=f"{ret_used:.1f}",
                 hist=f"{hist:.1f}%" if hist is not None else "—", months=f"{months:.0f}" if months else "—",
                 infl=f"{cfg['inv_inflation']:g}"))


def investments_total(api_key_id, api_secret, ccy):
    """(cost, valoare) pentru toate portofoliile, in moneda ccy; None daca nu exista date."""
    from positions_data import build_t212_frame
    from t212_api import fetch_account_currency, load_cached_snapshot
    snap = load_cached_snapshot() or {}
    errs = snap.get("errors") or {}
    has_t212 = bool(snap) and not (errs.get("cash") or errs.get("portfolio"))
    account_ccy = (fetch_account_currency(api_key_id, api_secret)[0] if has_t212 else None) or "?"
    df, *_ = build_t212_frame((snap.get("positions") or []) if has_t212 else [], snap.get("instruments") if has_t212 else None,
                              errs.get("instruments"), account_ccy, {}, {}, {})
    opts = [o for o in portfolio_options() if has_t212 or o != "Trading 212"]
    if not opts:
        return None
    vdf = build_rows(df, ccy, opts, account_ccy)
    if vdf.empty:
        return None
    return float(vdf["cost_disp"].sum()), float(vdf["value_disp"].sum()), opts


def render_summary(api_key_id, api_secret):
    cfg = pension.load()
    ccy = st.radio(t("pen.currency"), pension.CURRENCIES, index=pension.CURRENCIES.index(cfg["currency"]),
                   horizontal=True, key="summary_ccy")
    if ccy != cfg["currency"]:
        cfg = pension.save(dict(cfg, currency=ccy))
    rate = fx("RON", ccy) if ccy != "RON" else 1.0

    inv = None
    try:
        inv = investments_total(api_key_id, api_secret, ccy)
    except Exception as e:  # datele brokerilor pot lipsi; restul rezumatului ramane
        notice.card(t("sum.inv_error", e=str(e)[:200]))
    has_pension = bool(cfg["points"] or cfg["contrib_years"])
    r = pension.project(cfg) if has_pension else None
    pillars_now = (cfg["p2_balance"] + cfg["p3_balance"]) * rate

    st.subheader(t("sum.wealth_title"))
    c1, c2, c3 = st.columns(3)
    if inv:
        cost, value, opts = inv
        c1.metric(t("sum.investments"), _money(value, ccy), mask(f"{value - cost:+,.0f}".replace(",", ".")),
                  help=t("sum.investments_help", p=", ".join(opts), cost=_money(cost, ccy)))
    else:
        c1.metric(t("sum.investments"), "—", help=t("sum.no_investments"))
    c2.metric(t("sum.pillars_now"), _money(pillars_now, ccy),
              help=t("sum.pillars_now_help", p2=_money(cfg["p2_balance"] * rate, ccy), p3=_money(cfg["p3_balance"] * rate, ccy)))
    c3.metric(t("sum.total_now"), _money((inv[1] if inv else 0) + pillars_now, ccy), help=t("sum.total_now_help"))

    if inv:
        _projection(cfg, inv, ccy)

    st.subheader(t("sum.pension_title"))
    if not r:
        notice.card(t("pen.empty"), icon="ℹ️")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric(t("sum.state_net"), _money(r["pension_at_retire"] * rate, ccy),
              help=t("sum.state_net_help", date=f"{r['out_date'][1]:02d}.{r['out_date'][0]}", age=f"{r['age_out']:g}"))
    c2.metric(t("sum.pillars_retire"), _money((r["p2_at_retire"] + r["p3_at_retire"]) * rate, ccy), help=t("sum.pillars_retire_help"))
    c3.metric(t("sum.years_left"), f"{r['years_left']:.1f}")
    st.caption(t("sum.note"))
