"""Graficul valorii portofoliului in timp si mini-graficul variatiei profitului (pagina principala)."""
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import mobile
import privacy
from history_multi import multi_history_records
from core import load_portfolio_history
from i18n import t, x as _tx
from portfolio_model import fx as _fx
from privacy import mask as _mask


def _history_dialog(fig):
    st.dialog(_tx("Valoare de piață în timp"), width="large")(_history_dialog_inner)(fig)


def _history_dialog_inner(fig):
    big = go.Figure(fig)
    big.update_layout(height=560)
    mobile.plotly_chart(big, width="stretch", key="portfolio_history_chart_big")


def profit_sparkline(x, y, ccy):
    """Mini-grafic al variatiei profitului: verde peste zero, rosu sub zero (linie si umplere)."""
    xs = list(pd.to_datetime(x))
    ys = [float(v) for v in y]
    # la fiecare trecere prin zero se adauga punctul de intersectie, ca segmentele sa se lege
    px_, py_ = [xs[0]], [ys[0]]
    for i in range(1, len(ys)):
        a, b = ys[i - 1], ys[i]
        if (a < 0 < b) or (b < 0 < a):
            f = a / (a - b)
            px_.append(xs[i - 1] + (xs[i] - xs[i - 1]) * f)
            py_.append(0.0)
        px_.append(xs[i])
        py_.append(b)
    fig = go.Figure()
    for sign, color, fill in ((1, "#21c354", "rgba(33,195,84,0.18)"), (-1, "#ff4b4b", "rgba(255,75,75,0.18)")):
        seg = [v if v * sign >= 0 else None for v in py_]
        fig.add_trace(go.Scatter(
            x=px_, y=seg, mode="lines", line=dict(color=color, width=2), fill="tozeroy", fillcolor=fill,
            connectgaps=False, hoverinfo="skip",
        ))
    # hover doar din seria reala (invizibila), cu linie verticala si eticheta comuna, ca pe graficul mare
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="lines", line=dict(width=0), name=t("hist.spark_y", ccy=ccy),
        hovertemplate="%{y:+,.2f} " + ccy + "<extra></extra>",
    ))
    fig.update_layout(
        height=170, margin=dict(l=6, r=0, t=4, b=0), showlegend=False, font=dict(size=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
    )
    # formatul etichetelor de timp dupa pasul dintre ele: ore, zile, luni sau ani (fara 01.01 repetat la "Max")
    fig.update_xaxes(title_text=t("hist.spark_x"), title_standoff=4, fixedrange=True, nticks=4, showgrid=False,
                     hoverformat="%d.%m.%Y %H:%M",
                     tickformatstops=[
                         dict(dtickrange=[None, 86400000], value="%H:%M"),
                         dict(dtickrange=[86400000, "M1"], value="%d.%m"),
                         dict(dtickrange=["M1", "M12"], value="%m.%Y"),
                         dict(dtickrange=["M12", None], value="%Y"),
                     ])
    fig.update_yaxes(title_text=t("hist.spark_y", ccy=ccy), title_standoff=14, fixedrange=True, nticks=4,
                     tickformat="+,.0f", zeroline=True, zerolinecolor="rgba(128,128,128,0.6)")
    if privacy.hidden():
        fig.update_yaxes(showticklabels=False)
        fig.update_traces(hoverinfo="skip", hovertemplate=None)
    return fig


def render_history(sel_portfolios, display_ccy, native, compact, right_extra):
    """Graficul istoric cu alegerea perioadei; right_extra() se randeaza la final in coloana din dreapta.
    Intoarce True daca graficul a fost afisat (altfel istoricul abia se aduna)."""
    portfolio_history = multi_history_records(sel_portfolios, display_ccy)
    if native and len(portfolio_history) < 2:
        portfolio_history = load_portfolio_history()
    if len(portfolio_history) < 2:
        st.caption(t("hist.accumulating"))
        return False
    history_df = pd.DataFrame(portfolio_history)
    history_df["x"] = history_df["ts"].fillna(history_df["date"]) if "ts" in history_df.columns else history_df["date"]
    history_df["x"] = pd.to_datetime(history_df["x"], format="ISO8601")
    history_df = history_df.sort_values("x")
    _thr = 40.0 * float(_fx("EUR", display_ccy) or 1.0)
    if st.session_state.get("hist_hide_small", True):
        _f = history_df[history_df["invested"] >= _thr]
        if len(_f) >= 2:
            history_df = _f
    _first_all = history_df["x"].min()
    if st.session_state.get("history_range") not in ("3H", "1D", "1W", "1M", "1Y", "YTD", "Max"):
        _pref = st.session_state.get("_hist_range_pref")
        st.session_state["history_range"] = _pref if _pref in ("3H", "1D", "1W", "1M", "1Y", "YTD", "Max") else "YTD"
    st.checkbox(t("hist.hide_small", thr=f"{_thr:,.0f} {display_ccy}"), value=True, key="hist_hide_small")
    _hc_left, _hc_right = st.columns(2)
    with _hc_left:
        range_choice = mobile.period_picker(
            "Perioadă", ["3H", "1D", "1W", "1M", "1Y", "YTD", "Max"],
            key="history_range", label_visibility="collapsed",
        )
    st.session_state["_hist_range_pref"] = range_choice
    _now = pd.Timestamp(datetime.now())
    _deltas = {
        "3H": pd.Timedelta(hours=3), "1D": pd.Timedelta(days=1), "1W": pd.Timedelta(weeks=1),
        "1M": pd.Timedelta(days=30), "1Y": pd.Timedelta(days=365),
    }
    if range_choice == "YTD":
        _start = pd.Timestamp(_now.year, 1, 1)
    elif range_choice == "Max":
        _start = None
    else:
        _start = _now - _deltas[range_choice]
    if _start is not None:
        _sel = history_df[history_df["x"] >= _start]
        history_df = _sel if len(_sel) >= 2 else history_df.tail(2)
    history_df = history_df.copy()
    try:
        history_df["x"] = history_df["x"].dt.tz_localize("UTC").dt.tz_convert("Europe/Bucharest").dt.tz_localize(None)
    except Exception:
        pass
    _show_inv = range_choice in ("1M", "1Y", "YTD", "Max")
    _nowl = pd.Timestamp.now(tz="Europe/Bucharest").tz_localize(None)
    _first_local = pd.Timestamp(_first_all).tz_localize("UTC").tz_convert("Europe/Bucharest").tz_localize(None)
    if range_choice == "YTD":
        _ps = pd.Timestamp(_nowl.year, 1, 1)
    elif range_choice == "Max":
        _ps = None
    else:
        _ps = _nowl - _deltas[range_choice]
    with _hc_right:
        _pl_ser = history_df["market_value"] - history_df["invested"]
        _pl_d = float(_pl_ser.iloc[-1] - _pl_ser.iloc[0])
        _inv_avg = float(history_df["invested"].mean())
        _var_col, _spark_col = st.columns([1, 1], vertical_alignment="center")
        _var_col.metric(
            t("hist.variation", rng=range_choice), _mask(f"{_pl_d:+,.2f} {display_ccy}"),
            f"{_pl_d / _inv_avg * 100:+.2f}%" if _inv_avg else None,
        )
        with _spark_col:
            # variatia profitului fata de inceputul perioadei
            _spark_fig = profit_sparkline(history_df["x"], _pl_ser - float(_pl_ser.iloc[0]), display_ccy)
            st.plotly_chart(_spark_fig, width="stretch", key="profit_sparkline",
                            config={"displayModeBar": False, "staticPlot": privacy.hidden()})
        if not compact:
            st.caption(t("hist.variation_help"))
            st.caption(t("hist.points", n=len(history_df), a=f"{history_df['x'].iloc[0]:%d.%m %H:%M}", b=f"{history_df['x'].iloc[-1]:%d.%m %H:%M}"))
        if not compact and _ps is not None and _first_local > _ps + pd.Timedelta(minutes=30):
            st.caption(t("hist.incomplete", d=f"{_first_local:%d.%m.%Y %H:%M}"))
        right_extra()
    history_fig = go.Figure()
    history_fig.add_trace(
        go.Scatter(
            x=history_df["x"],
            y=history_df["market_value"],
            name=_tx("Valoare de piață"),
            mode="lines",
            line=dict(color="#4da3ff", width=2.5),
        )
    )
    if _show_inv:
        history_fig.add_trace(
            go.Scatter(
                x=history_df["x"],
                y=history_df["invested"],
                name=_tx("Investit"),
                mode="lines",
                line=dict(dash="dot", color="#ff9f43", width=2.5),
            )
        )
    history_fig.update_layout(
        title=f"{_tx('Valoare de piață în timp')} ({display_ccy})",
        height=300,
        margin=dict(l=10, r=10, t=60, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    if _show_inv:
        _lo = float(min(history_df["market_value"].min(), history_df["invested"].min()))
        _hi = float(max(history_df["market_value"].max(), history_df["invested"].max()))
        _pad = max((_hi - _lo) * 0.15, _hi * 0.01)
        history_fig.update_yaxes(range=[_lo - _pad, _hi + _pad])
    else:
        _lo = float(history_df["market_value"].min())
        _hi = float(history_df["market_value"].max())
        _pad = max((_hi - _lo) * 0.25, _hi * 0.0005)
        history_fig.update_yaxes(range=[_lo - _pad, _hi + _pad], tickformat=",.0f")
    history_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    history_fig.update_layout(hovermode="x unified")
    history_fig.update_traces(hovertemplate="%{y:,.2f}")
    if privacy.hidden():
        # forma curbei ramane, valorile nu (fara axa Y si fara hover)
        history_fig.update_yaxes(showticklabels=False)
        history_fig.update_traces(hoverinfo="skip", hovertemplate=None)
    _x1 = pd.Timestamp.now(tz="Europe/Bucharest").tz_localize(None)
    if range_choice == "YTD":
        _x0 = pd.Timestamp(_x1.year, 1, 1)
    elif range_choice == "Max":
        _x0 = history_df["x"].min()
    else:
        _x0 = _x1 - _deltas[range_choice]
    _x0 = min(_x0, history_df["x"].min())
    history_fig.update_xaxes(range=[_x0, _x1])
    if len(history_df) <= 40:
        history_fig.update_traces(mode="lines+markers", marker=dict(size=5))
    with _hc_left:
        mobile.plotly_chart(history_fig, width="stretch", key="portfolio_history_chart")
        _enlarge = not compact and st.button(t("hist.enlarge"), key="history_enlarge")
    if _enlarge:
        _history_dialog(history_fig)
    return True
