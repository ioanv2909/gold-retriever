"""Tab-ul Expunere: rotatia sectoarelor (RRG + expunerea ta) si expunerea portofoliului pe factori."""
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import mobile

import exposure
import factors
import rotation
from i18n import t

# cadranele RRG, din paleta categoriala a aplicatiei; numele cadranului sta si scris in colt (nu doar culoarea)
Q_COLORS = {"leading": "#1baf7a", "weakening": "#eda100", "lagging": "#eb6834", "improving": "#2a78d6"}
POS, NEG = "#2a78d6", "#eb6834"   # coeficienti de factor: peste / sub zero
ETFS = tuple(list(rotation.SECTOR_ETFS.values()) + [rotation.BENCH] + list(factors.FACTORS.values()))


def _closes(symbols):
    from compare_ui import get_closes
    return get_closes(tuple(symbols), "2y", "1wk")


def _sector_label(sector):
    name = t("ex.sector." + sector)
    return sector if name.startswith("ex.sector.") else name


def _sector_pct(rows, meta):
    return {k: p for k, _, p in exposure.breakdown(rows, meta, "sector") if k in rotation.SECTOR_ETFS}


def _rrg_chart(points, pct):
    fig = go.Figure()
    xs = [x for p in points.values() for x in p["ratio"]]
    ys = [y for p in points.values() for y in p["mom"]]
    dx = max(2.0, max(abs(x - 100) for x in xs) * 1.15)
    dy = max(2.0, max(abs(y - 100) for y in ys) * 1.15)
    corners = {"leading": (1, 1), "weakening": (1, -1), "lagging": (-1, -1), "improving": (-1, 1)}
    for q, (sx, sy) in corners.items():
        fig.add_shape(type="rect", x0=100, x1=100 + sx * dx, y0=100, y1=100 + sy * dy, layer="below",
                      line_width=0, fillcolor=Q_COLORS[q], opacity=0.07)
        fig.add_annotation(x=100 + sx * dx * 0.97, y=100 + sy * dy * 0.95, text="<b>%s</b>" % t("rot.q." + q),
                           showarrow=False, xanchor="right" if sx > 0 else "left", font={"size": 12},
                           opacity=0.7)
    for sector, p in points.items():
        color = Q_COLORS[p["quadrant"]]
        w = pct.get(sector, 0.0)
        label = _sector_label(sector)
        fig.add_trace(go.Scatter(x=p["ratio"], y=p["mom"], mode="lines", line={"color": color, "width": 2},
                                 opacity=0.45, hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=[p["ratio"][-1]], y=[p["mom"][-1]], mode="markers+text", showlegend=False,
            marker={"color": color, "size": 9 + 4 * math.sqrt(w), "line": {"width": 2, "color": "#ffffff"}},
            text=["<b>%s</b>" % label if w else label], textposition="top center",
            hovertemplate="%s · %s<br>RS-Ratio %.1f · RS-Momentum %.1f<br>%s<extra></extra>" % (
                label, t("rot.q." + p["quadrant"]), p["ratio"][-1], p["mom"][-1], t("rot.hover_weight", p="%.1f" % w))))
    fig.add_hline(y=100, line_width=1, line_color="rgba(128,128,128,0.5)")
    fig.add_vline(x=100, line_width=1, line_color="rgba(128,128,128,0.5)")
    fig.update_layout(height=520, margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis={"title": "RS-Ratio", "range": [100 - dx, 100 + dx], "showgrid": False, "zeroline": False},
                      yaxis={"title": "RS-Momentum", "range": [100 - dy, 100 + dy], "showgrid": False,
                             "zeroline": False})
    return fig


def render_rotation(rows, meta):
    st.caption(t("rot.caption"))
    with st.spinner(t("rot.loading")):
        closes = _closes(ETFS)
    points = rotation.rrg(closes)
    if not points:
        st.info(t("rot.no_data"))
        return
    pct = _sector_pct(rows, meta)
    by_q = rotation.portfolio_by_quadrant(pct, points)
    cols = st.columns(4)
    for c, q in zip(cols, rotation.QUADRANTS):
        c.metric(t("rot.q." + q), "%.0f%%" % by_q[q], help=t("rot.q_help." + q))
    st.caption(t("rot.other", p="%.0f" % (100 - sum(by_q[q] for q in rotation.QUADRANTS))))
    mobile.plotly_chart(_rrg_chart(points, pct), width="stretch", key="rot_chart")
    st.caption(t("rot.chart_note"))

    rel = rotation.relative_returns(closes)
    order = {q: i for i, q in enumerate(rotation.QUADRANTS)}
    table = []
    for sector, p in sorted(points.items(), key=lambda kv: (order[kv[1]["quadrant"]], -kv[1]["ratio"][-1])):
        row = {t("rot.col.sector"): _sector_label(sector), "ETF": rotation.SECTOR_ETFS[sector],
               t("rot.col.quadrant"): t("rot.q." + p["quadrant"])}
        for n in rotation.RETURN_WEEKS:
            v = (rel.get(sector) or {}).get(n)
            row[t("rot.col.vs", n=t("rot.w.%d" % n))] = round(v, 1) if v is not None else None
        row[t("rot.col.weight")] = round(pct.get(sector, 0.0), 1)
        table.append(row)
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch", column_config={
        t("rot.col.weight"): st.column_config.NumberColumn(t("rot.col.weight"), format="%.1f%%",
                                                           help=t("rot.col.weight_help")),
        **{t("rot.col.vs", n=t("rot.w.%d" % n)): st.column_config.NumberColumn(
            t("rot.col.vs", n=t("rot.w.%d" % n)), format="%+.1f pp", help=t("rot.col.vs_help"))
           for n in rotation.RETURN_WEEKS}})
    st.caption(t("rot.disclaimer"))


def _weights(vdf):
    w = {}
    for r in vdf.to_dict("records"):
        sym, v = r.get("yahoo_symbol"), r.get("value_disp")
        if sym and v and v == v and v > 0:
            w[sym] = w.get(sym, 0.0) + float(v)
    return w


def _factor_chart(res):
    names = list(res["tilts"])
    coef = [res["tilts"][f][0] for f in names]
    tval = [res["tilts"][f][1] for f in names]
    sig = [abs(x) >= factors.T_SIGNIFICANT for x in tval]
    labels = [t("fac.f." + f) for f in names]
    fig = go.Figure(go.Bar(
        y=labels, x=coef, orientation="h",
        marker={"color": [POS if c >= 0 else NEG for c in coef], "opacity": [1.0 if s else 0.4 for s in sig],
                "cornerradius": 4},
        text=["%+.2f%s" % (c, "" if s else " *") for c, s in zip(coef, sig)], textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}: %{x:+.2f}<br>t = %{customdata:.1f}<extra></extra>", customdata=tval))
    m = max(0.2, max(abs(c) for c in coef) * 1.3)
    fig.add_vline(x=0, line_width=1, line_color="rgba(128,128,128,0.6)")
    fig.update_layout(height=60 + 40 * len(names), margin={"l": 10, "r": 40, "t": 10, "b": 10}, bargap=0.35,
                      xaxis={"range": [-m, m], "zeroline": False, "showgrid": False},
                      yaxis={"autorange": "reversed"}, showlegend=False)
    return fig


def render_factors(vdf):
    st.caption(t("fac.caption"))
    weights = _weights(vdf)
    if not weights:
        st.info(t("ex.empty"))
        return
    with st.spinner(t("rot.loading")):
        bench = _closes(ETFS)
        prices = _closes(tuple(sorted(weights)))
    port, coverage = factors.portfolio_returns(prices, weights)
    res = factors.regress(port, bench)
    if not res:
        st.info(t("fac.no_data"))
        return
    c1, c2, c3 = st.columns(3)
    c1.metric(t("fac.beta"), "%.2f" % res["beta"], help=t("fac.beta_help"))
    c2.metric("R²", "%.0f%%" % (res["r2"] * 100) if res["r2"] is not None else "n/a", help=t("fac.r2_help"))
    c3.metric(t("fac.coverage"), "%.0f%%" % coverage, help=t("fac.coverage_help", n=res["n"]))
    mobile.plotly_chart(_factor_chart(res), width="stretch", key="fac_chart")
    st.caption(t("fac.chart_note"))
    with st.expander(t("ex.table")):
        st.dataframe(pd.DataFrame([{
            t("fac.col.factor"): t("fac.f." + f), "ETF": factors.FACTORS[f], t("fac.col.coef"): round(c, 2),
            "t": round(tv, 1), t("fac.col.meaning"): t("fac.why." + f),
        } for f, (c, tv) in res["tilts"].items()]), hide_index=True, width="stretch")
    st.caption(t("fac.disclaimer"))
