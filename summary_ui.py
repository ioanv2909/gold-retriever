"""Sectiunea Rezumat: investitiile si pensiile intr-un singur loc (fiecare cu ce reprezinta).

Contine: averea de azi (cu schimbarea fata de acum o luna si de la 1 ianuarie), proiectia investitiilor la bursa
(depunere lunara, randament, inflatie), obiectivul de avere, graficul "drumul spre pensie" si ce primesti la
pensionare (pensia de stat, pilonii II/III, venitul din investitii dupa regula de 4%). Pe telefon doar cifrele
mari si graficul.
"""
from datetime import datetime, timedelta

import streamlit as st

import mobile
import notice
import pension
from i18n import t
from portfolio_model import build_rows, fx, portfolio_options
from privacy import mask

_SYMBOL = {"RON": "lei", "EUR": "EUR", "USD": "USD"}
WITHDRAW_RATE = 4.0  # regula de 4%: retragere anuala sustenabila din investitii


def _money(v, ccy):
    return mask(f"{v:,.0f} {_SYMBOL.get(ccy, ccy)}".replace(",", "."))


def history(opts, ccy):
    """(depuneri nete, luni, ritm lunar) din jurnalul operatiunilor, pentru portofoliile date, in ccy."""
    import journal
    import pace_target
    ops = [op for op in journal.load_all({}) if op["type"] in ("deposit", "withdrawal", "buy")]
    _, net, months, pace = pace_target.pace_of(ops, ccy, set(opts))
    return net, months, pace


def investments_total(api_key_id, api_secret, ccy):
    """(cost, valoare, portofolii) pentru toate portofoliile, in moneda ccy; None daca nu exista date."""
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


def projection_inputs(cfg, ccy, api_key_id=None, api_secret=None):
    """Datele proiectiei investitiilor in ccy: valoarea de azi (pozitii + cash neinvestit), depunerea lunara,
    randamentul folosit, randamentul istoric, lunile de istoric si ritmul lunar. None fara date de la brokeri."""
    if api_key_id is None:
        from core import load_config
        c = load_config()
        api_key_id, api_secret = c.get("api_key_id"), c.get("api_secret")
    inv = investments_total(api_key_id, api_secret, ccy)
    if not inv:
        return None
    cost, value, opts = inv
    try:
        net, months, pace = history(opts, ccy)
    except Exception:  # jurnalul poate lipsi: proiectia merge si fara istoric
        net, months, pace = None, None, None
    now_value = value + max(0.0, (net or 0) - cost)
    hist = pension.uniform_return(net, months, now_value) if net and months else None
    inv_rate = fx(cfg["inv_ccy"], ccy) if cfg["inv_ccy"] != ccy else 1.0
    monthly = cfg["inv_monthly"] * (inv_rate or 1) if cfg["inv_monthly"] else (pace or 0)
    ret = cfg["inv_return"] if cfg["inv_return"] > -99 else (hist if hist is not None else 6.0)
    return {"cost": cost, "value": value, "opts": opts, "now": now_value, "monthly": monthly, "ret": ret,
            "hist": hist, "months": months, "pace": pace, "inv_rate": inv_rate or 1}


def _changes(opts, ccy):
    """Schimbarea investitiilor fata de acum ~o luna si de la 1 ianuarie: (valoare, castig din piata) per perioada.
    Castigul din piata = schimbarea (valoare - investit), adica fara depunerile noi."""
    from history_multi import multi_history_records
    rec = [r for r in multi_history_records(opts, ccy) if r.get("market_value") is not None]
    if len(rec) < 2:
        return {}
    last = rec[-1]
    now = datetime.fromisoformat(last["ts"][:19])
    out = {}
    for key, since in (("month", now - timedelta(days=30)), ("ytd", datetime(now.year, 1, 1))):
        base = next((r for r in rec if datetime.fromisoformat(r["ts"][:19]) >= since), None)
        if base is None or base is last:
            continue
        dv = last["market_value"] - base["market_value"]
        dg = (last["market_value"] - last["invested"]) - (base["market_value"] - base["invested"])
        out[key] = {"value": dv, "gain": dg, "pct": dg / base["market_value"] * 100 if base["market_value"] else None,
                    "since": base["ts"][:10]}
    return out


def _form(cfg, p, ccy):
    with st.form("invest_projection"):
        c1, c2, c3, c4 = st.columns(4)
        m_ccy = c1.selectbox(t("sum.proj_ccy"), pension.CURRENCIES, index=pension.CURRENCIES.index(cfg["inv_ccy"]))
        default_m = cfg["inv_monthly"] or ((p["pace"] or 0) / p["inv_rate"])
        monthly = c2.number_input(t("sum.proj_monthly"), 0.0, 1e7, float(round(default_m, 0)), 50.0,
                                  help=t("sum.proj_monthly_help", pace=_money(p["pace"] or 0, ccy)))
        default_r = cfg["inv_return"] if cfg["inv_return"] > -99 else round(p["hist"] if p["hist"] is not None else 6.0, 1)
        ret = c3.number_input(t("sum.proj_return"), -10.0, 30.0, float(default_r), 0.1,
                              help=t("sum.proj_return_help", hist=f"{p['hist']:.1f}%" if p["hist"] is not None else "—"))
        infl = c4.number_input(t("sum.proj_inflation"), 0.0, 30.0, float(cfg["inv_inflation"]), 0.1)
        c1, c2, _, _ = st.columns(4)
        goal = c1.number_input(t("sum.goal_amount"), 0.0, 1e10, float(cfg["goal_amount"]), 10000.0, help=t("sum.goal_help"))
        goal_age = c2.number_input(t("sum.goal_age"), 30.0, 80.0, float(cfg["goal_age"]), 1.0)
        if st.form_submit_button(t("sum.proj_save")):
            cfg = pension.save(dict(cfg, inv_ccy=m_ccy, inv_monthly=monthly, inv_return=ret, inv_inflation=infl,
                                    goal_amount=goal, goal_age=goal_age))
            st.rerun()
    return cfg


def _chart(cfg, p, ccy, height=380):
    import plotly.graph_objects as go
    path = pension.wealth_path(cfg, p["now"], p["monthly"], p["ret"], cfg["inv_inflation"],
                               until_age=max(67, cfg["goal_age"] if cfg["goal_amount"] else 0))
    ages = [round(x["age"], 1) for x in path]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ages, y=[x["total_high"] for x in path], line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=ages, y=[x["total_low"] for x in path], line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(0,208,132,0.15)", name=t("sum.chart_band"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=ages, y=[x["total"] for x in path], name=t("sum.chart_total"), line=dict(color="#00d084", width=3)))
    fig.add_trace(go.Scatter(x=ages, y=[x["inv"] for x in path], name=t("sum.chart_inv"), line=dict(color="#4a9eff", dash="dot")))
    fig.add_trace(go.Scatter(x=ages, y=[x["pillars"] for x in path], name=t("sum.chart_pillars"), line=dict(color="#f5a623", dash="dot")))
    chosen = cfg["planned_age"] or cfg["retire_age"]
    fig.add_vline(x=chosen, line_dash="dash", line_color="#9aa0a6", annotation_text=t("sum.chart_retire", age=f"{chosen:g}"))
    if cfg["goal_amount"]:
        goal = cfg["goal_amount"] * p["inv_rate"]
        fig.add_trace(go.Scatter(x=[cfg["goal_age"]], y=[goal], mode="markers", marker=dict(symbol="star", size=16, color="#ff6b6b"),
                                 name=t("sum.chart_goal")))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15), yaxis_title=_SYMBOL.get(ccy, ccy),
                      xaxis_title=t("sum.chart_age"))
    if not mobile.compact():
        fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, width="stretch", key="wealth_path_chart", config={"displayModeBar": False})
    st.caption(t("sum.chart_note", ret=f"{p['ret']:.1f}", infl=f"{cfg['inv_inflation']:g}"))


def _goal(cfg, p, ccy):
    if not cfg["goal_amount"]:
        return
    today = datetime.now()
    age_now = (today.year * 12 + today.month - 1 - (cfg["birth_year"] * 12 + cfg["birth_month"] - 1)) / 12
    months = round((cfg["goal_age"] - age_now) * 12)
    if months <= 0:
        return
    real = pension.real_return(p["ret"], cfg["inv_inflation"])
    pillars = (pension.future_value(cfg["p2_balance"], cfg["p2_monthly"], cfg["p2_return"], months)
               + pension.future_value(cfg["p3_balance"], cfg["p3_monthly"], cfg["p3_return"], months))
    goal = cfg["goal_amount"] * p["inv_rate"]
    need = pension.required_monthly(goal - pillars, p["now"], real, months)
    expected = pension.future_value(p["now"], p["monthly"], real, months) + pillars
    ok = need is not None and p["monthly"] >= need - 1e-6
    text = t("sum.goal_ok" if ok else "sum.goal_short", goal=_money(goal, ccy), age=f"{cfg['goal_age']:g}",
             need=_money(need or 0, ccy), monthly=_money(p["monthly"], ccy), expected=_money(expected, ccy))
    notice.card(text, icon="🎯" if ok else "⚠️", color="#00d084" if ok else "#f5a623")


def render_summary(api_key_id, api_secret):
    compact = mobile.compact()
    cfg = pension.load()
    ccy = st.radio(t("pen.currency"), pension.CURRENCIES, index=pension.CURRENCIES.index(cfg["currency"]),
                   horizontal=True, key="summary_ccy")
    if ccy != cfg["currency"]:
        cfg = pension.save(dict(cfg, currency=ccy))
    rate = fx("RON", ccy) if ccy != "RON" else 1.0

    p = None
    try:
        p = projection_inputs(cfg, ccy, api_key_id, api_secret)
    except Exception as e:  # datele brokerilor pot lipsi; restul rezumatului ramane
        notice.card(t("sum.inv_error", e=str(e)[:200]))
    has_pension = bool(cfg["points"] or cfg["contrib_years"])
    r = pension.project(cfg) if has_pension else None
    pillars_now = (cfg["p2_balance"] + cfg["p3_balance"]) * rate

    st.subheader(t("sum.wealth_title"))
    c1, c2, c3 = st.columns(3)
    if p:
        c1.metric(t("sum.investments"), _money(p["value"], ccy), mask(f"{p['value'] - p['cost']:+,.0f}".replace(",", ".")),
                  help=t("sum.investments_help", p=", ".join(p["opts"]), cost=_money(p["cost"], ccy)))
    else:
        c1.metric(t("sum.investments"), "—", help=t("sum.no_investments"))
    c2.metric(t("sum.pillars_now"), _money(pillars_now, ccy),
              help=t("sum.pillars_now_help", p2=_money(cfg["p2_balance"] * rate, ccy), p3=_money(cfg["p3_balance"] * rate, ccy)))
    c3.metric(t("sum.total_now"), _money((p["value"] if p else 0) + pillars_now, ccy), help=t("sum.total_now_help"))
    if p:
        try:
            ch = _changes(p["opts"], ccy)
        except Exception:
            ch = {}
        parts = []
        for key in ("month", "ytd"):
            if key in ch:
                x = ch[key]
                arrow = "🟢 ▲" if x["gain"] >= 0 else "🔴 ▼"
                parts.append(t("sum.change_" + key, arrow=arrow, gain=_money(x["gain"], ccy),
                               pct=f"{x['pct']:+.1f}" if x["pct"] is not None else "—", value=_money(x["value"], ccy)))
        if parts:
            st.markdown(" · ".join(parts))

    if p:
        st.subheader(t("sum.proj_title"))
        if not compact:
            cfg = _form(cfg, p, ccy)
            p = projection_inputs(cfg, ccy, api_key_id, api_secret)
        _chart(cfg, p, ccy, height=260 if compact else 380)
        _goal(cfg, p, ccy)
        if not compact:
            rows = pension.invest_by_age(cfg, p["now"], p["monthly"], p["ret"], cfg["inv_inflation"])
            chosen = cfg["planned_age"] or cfg["retire_age"]
            import pandas as pd
            out = [{t("pen.col_age"): (f"▶ {x['age']:g}" if abs(x["age"] - chosen) < 1e-9 else f"{x['age']:g}"),
                    t("pen.col_year"): f"{x['date'][1]:02d}.{x['date'][0]}",
                    t("sum.proj_col_paid"): _money(x["paid_in"], ccy),
                    t("sum.proj_col_value"): _money(x["value"], ccy),
                    t("sum.proj_col_gain"): _money(x["value"] - x["paid_in"], ccy),
                    t("sum.proj_col_real"): _money(x["real"], ccy),
                    t("sum.proj_col_income"): _money(x["real"] * WITHDRAW_RATE / 100 / 12, ccy)} for x in rows]
            st.dataframe(pd.DataFrame(out), hide_index=True, width="content")
            st.caption(t("sum.proj_note", now=_money(p["now"], ccy), monthly=_money(p["monthly"], ccy), ret=f"{p['ret']:.1f}",
                         hist=f"{p['hist']:.1f}%" if p["hist"] is not None else "—",
                         months=f"{p['months']:.0f}" if p["months"] else "—", infl=f"{cfg['inv_inflation']:g}"))

    st.subheader(t("sum.pension_title"))
    if not r:
        notice.card(t("pen.empty"), icon="ℹ️")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("sum.state_net"), _money(r["pension_at_retire"] * rate, ccy),
              help=t("sum.state_net_help", date=f"{r['out_date'][1]:02d}.{r['out_date'][0]}", age=f"{r['age_out']:g}"))
    c2.metric(t("sum.pillars_retire"), _money((r["p2_at_retire"] + r["p3_at_retire"]) * rate, ccy), help=t("sum.pillars_retire_help"))
    if p:
        inv_at = pension.invest_by_age(cfg, p["now"], p["monthly"], p["ret"], cfg["inv_inflation"], ages=(r["age_out"],))
        inv_at = next((x for x in inv_at if abs(x["age"] - r["age_out"]) < 1e-9), None)
        if inv_at:
            c3.metric(t("sum.inv_income"), _money(inv_at["real"] * WITHDRAW_RATE / 100 / 12, ccy),
                      help=t("sum.inv_income_help", value=_money(inv_at["real"], ccy)))
    c4.metric(t("sum.years_left"), f"{r['years_left']:.1f}")
    st.caption(t("sum.note"))
