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
