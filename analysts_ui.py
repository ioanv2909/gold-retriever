"""Sectiunea Analisti din pagina pozitiei: tinte de pret, recomandari, estimari, revizuiri, schimbari de rating."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import mobile

import analysts
from i18n import t
from yf_compat import yf, YFINANCE_AVAILABLE

# divergent: albastru = cumpara, gri = pastreaza, rosu = vinde (etichete text pe segmente, nu doar culoare)
REC_COLORS = {"strongBuy": "#184f95", "buy": "#6da7ec", "hold": "#9a9994", "sell": "#ec8a89", "strongSell": "#b52f2f"}
MUTED = "#9a9994"
INK = "#2a78d6"
CURRENT = "#e07b39"  # vizibil si pe tema deschisa, si pe cea inchisa


@st.cache_data(ttl=21600, show_spinner=False)
def get_analyst_data(yahoo_symbol):
    if not YFINANCE_AVAILABLE:
        return None
    try:
        tk = yf.Ticker(yahoo_symbol)
        try:
            raw_ccy = tk.fast_info.get("currency")
        except Exception:
            raw_ccy = None
        return analysts.fetch_analyst_data(tk, 100.0 if raw_ccy == "GBp" else 1.0)
    except Exception:
        return None


def _fmt(v, d=2):
    return f"{v:,.{d}f}" if v is not None else "n/a"


def _pct(v):
    return f"{v:+.1f}%" if v is not None else "n/a"


def _big(v):
    if v is None:
        return "n/a"
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(v) >= div:
            return f"{v / div:,.2f}{suf}"
    return f"{v:,.0f}"


def _target_chart(tg, price, ccy):
    """Intervalul low-high al tintelor, cu media si pretul curent marcate."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[tg["low"], tg["high"]], y=[0, 0], mode="lines", line={"color": MUTED, "width": 6},
        hovertemplate="%{x:,.2f} " + ccy + "<extra></extra>", showlegend=False))
    marks = [(t("an.low"), tg["low"], MUTED, "line-ns"), (t("an.high"), tg["high"], MUTED, "line-ns"),
             (t("an.mean"), tg["mean"], INK, "diamond"), (t("an.current"), price, CURRENT, "circle")]
    for i, (label, x, color, symbol) in enumerate(marks):
        if x is None:
            continue
        fig.add_trace(go.Scatter(
            x=[x], y=[0], mode="markers+text", name=label, text=[f"{label}<br>{x:,.2f}"],
            textposition="top center" if i % 2 else "bottom center",
            marker={"color": color, "size": 14 if symbol != "line-ns" else 18, "symbol": symbol,
                    "line": {"width": 2, "color": color if symbol == "line-ns" else "white"}},
            hovertemplate=label + ": %{x:,.2f} " + ccy + "<extra></extra>", showlegend=False))
    fig.update_layout(height=150, margin={"l": 10, "r": 10, "t": 30, "b": 30},
                      yaxis={"visible": False, "range": [-1, 1]},
                      xaxis={"showgrid": False, "zeroline": False, "ticksuffix": " " + ccy})
    return fig


def _rec_chart(recs):
    """Distributia recomandarilor pe ultimele luni, 100% pe bara."""
    labels = {"0m": t("an.month_now")}
    periods = [labels.get(r["period"], t("an.months_ago", n=r["period"].lstrip("-").rstrip("m"))) for r in recs]
    fig = go.Figure()
    for col in analysts.REC_COLS:
        vals = [r[col] / r["total"] * 100 for r in recs]
        fig.add_trace(go.Bar(
            y=periods, x=vals, orientation="h", name=t("an.rec." + col), marker={"color": REC_COLORS[col],
            "line": {"color": "rgba(0,0,0,0)", "width": 2}},
            text=[str(r[col]) if r[col] else "" for r in recs], textposition="inside", insidetextanchor="middle",
            customdata=[r[col] for r in recs],
            hovertemplate="%{y} · " + t("an.rec." + col) + ": %{customdata} (%{x:.0f}%)<extra></extra>"))
    fig.update_layout(barmode="stack", bargap=0.35, height=60 + 38 * len(recs),
                      margin={"l": 10, "r": 10, "t": 10, "b": 10}, xaxis={"visible": False, "range": [0, 100]},
                      yaxis={"autorange": "reversed"},
                      legend={"orientation": "h", "y": -0.15, "traceorder": "normal"})
    return fig


def _estimates_table(est, revenue=False):
    rows = []
    for p in analysts.EST_PERIODS:
        e = est.get(p)
        if not e:
            continue
        f = _big if revenue else _fmt
        rows.append({
            t("an.col.period"): t("an.period." + p),
            t("an.col.avg"): f(e["avg"]),
            t("an.col.range"): f"{f(e['low'])} – {f(e['high'])}",
            t("an.col.year_ago"): f(e["year_ago"]),
            t("an.col.growth"): _pct(e["growth"]),
            t("an.col.analysts"): e["n"] if e["n"] is not None else "n/a",
        })
    return pd.DataFrame(rows)


def _trend_table(trend):
    rows = []
    for p in analysts.EST_PERIODS:
        e = trend.get(p)
        if not e or e.get("current") is None:
            continue
        rows.append({
            t("an.col.period"): t("an.period." + p),
            t("an.col.eps_now"): _fmt(e["current"]),
            t("an.col.chg_30d"): _pct(e.get("chg_30d")),
            t("an.col.chg_90d"): _pct(e.get("chg_90d")),
            t("an.col.up_down"): f"↑{e.get('up_30d') or 0} / ↓{e.get('down_30d') or 0}",
        })
    return pd.DataFrame(rows)


def render_analyst_section(yahoo_symbol, price, ccy, key):
    st.subheader(t("an.title"))
    data = get_analyst_data(yahoo_symbol)
    if not analysts.has_data(data):
        st.info(t("an.no_data"))
        return

    tg = data.get("targets")
    if tg:
        ref = tg.get("current") or price
        n = data["recommendations"][0]["total"] if data.get("recommendations") else None
        c = st.columns(4)
        c[0].metric(t("an.mean"), f"{_fmt(tg['mean'])} {ccy}", _pct(analysts.upside(tg["mean"], ref)), help=t("an.help_mean"))
        c[1].metric(t("an.median"), f"{_fmt(tg['median'])} {ccy}", _pct(analysts.upside(tg["median"], ref)))
        c[2].metric(t("an.low_high"), f"{_fmt(tg['low'])} – {_fmt(tg['high'])}",
                    f"{_pct(analysts.upside(tg['low'], ref))} / {_pct(analysts.upside(tg['high'], ref))}", delta_color="off")
        c[3].metric(t("an.n_analysts"), n if n is not None else "n/a")
        mobile.plotly_chart(_target_chart(tg, ref, ccy), width="stretch", key=f"an_tg_{key}")

    if data.get("recommendations"):
        st.markdown("**" + t("an.recs_title") + "**")
        mobile.plotly_chart(_rec_chart(data["recommendations"]), width="stretch", key=f"an_rec_{key}")

    if data.get("eps"):
        eps_ccy = next((e.get("currency") for e in data["eps"].values() if e.get("currency")), "")
        st.markdown("**" + t("an.eps_title", ccy=eps_ccy) + "**")
        st.dataframe(_estimates_table(data["eps"]), hide_index=True, width="stretch")
    if data.get("revenue"):
        rev_ccy = next((e.get("currency") for e in data["revenue"].values() if e.get("currency")), "")
        st.markdown("**" + t("an.rev_title", ccy=rev_ccy) + "**")
        st.dataframe(_estimates_table(data["revenue"], revenue=True), hide_index=True, width="stretch")
    trend = _trend_table(data.get("eps_trend") or {})
    if not trend.empty:
        st.markdown("**" + t("an.trend_title") + "**", help=t("an.help_trend"))
        st.dataframe(trend, hide_index=True, width="stretch")

    if data.get("changes"):
        with st.expander(t("an.changes_title")):
            st.dataframe(pd.DataFrame([{
                t("an.col.date"): c["date"],
                t("an.col.firm"): c["firm"],
                t("an.col.action"): t("an.action." + c["action"]) if c["action"] in ("up", "down", "main", "init", "reit") else c["action"],
                t("an.col.grade"): f"{c['from']} → {c['to']}" if c["from"] and c["from"] != c["to"] else c["to"],
                t("an.col.target"): (f"{_fmt(c['prior_target'])} → " if c["prior_target"] else "") + _fmt(c["target"])
                if c["target"] else "",
            } for c in data["changes"]]), hide_index=True, width="stretch")
    st.caption(t("an.source"))
