"""Graficul valorii portofoliului in timp si mini-graficul variatiei profitului (pagina principala)."""
from datetime import datetime

import html
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import mobile
import privacy
from history_multi import multi_history_records, to_local
from core import load_portfolio_history
from i18n import t, x as _tx
from portfolio_model import fx as _fx
from privacy import mask as _mask
import benchmark
from lang_prefs import load_pref, save_pref
from yf_compat import yf, YFINANCE_AVAILABLE

# perioadele graficului de valoare; pe telefon doar o parte, cele lipsa trec la cea mai apropiata
HIST_RANGES = ("3H", "1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "Max")
HIST_RANGES_COMPACT = ("1D", "1W", "1M", "3M", "YTD", "1Y", "Max")
_HIST_NEAR_COMPACT = {"3H": "1D", "6M": "3M", "3Y": "1Y", "5Y": "Max"}


LINES = ("value", "sp500", "invested")
_LINE_COLORS = {"value": "#4da3ff", "sp500": "#1baf7a", "invested": "#ff9f43"}


@st.cache_data(ttl=900, show_spinner=False)
def sp500_prices(range_choice, ccy):
    """Pretul S&P 500 in moneda ccy (ora locala, fara fus orar), sau None daca Yahoo nu raspunde."""
    if not YFINANCE_AVAILABLE:
        return None
    period, interval = benchmark.YF_RANGE.get(range_choice, ("max", "1d"))
    try:
        px = benchmark.to_local_naive(
            yf.Ticker(benchmark.SYMBOL).history(period=period, interval=interval, timeout=10)["Close"])
        if px.empty:
            return None
        if ccy != "USD":
            fx = None
            try:
                fx = benchmark.to_local_naive(
                    yf.Ticker(f"USD{ccy}=X").history(period=period, interval=interval, timeout=10)["Close"])
            except Exception:
                pass
            if fx is not None and not fx.empty:
                px = px * benchmark.align(px.index, fx).to_numpy()
            else:
                px = px * float(_fx("USD", ccy) or 1.0)
        if interval == "1d":
            # pretul zilnic e datat la miezul noptii la New York; il punem la ora inchiderii (22:00 la noi)
            px.index = px.index.normalize() + pd.Timedelta(hours=22)
        return px
    except Exception:
        return None


def _line_label(k):
    return {"value": "🔵 ", "sp500": "🟢 ", "invested": "🟠 "}[k] + t("hist.line." + k)


def _history_dialog(fig):
    st.dialog(_tx("Valoare de piață în timp"), width="large")(_history_dialog_inner)(fig)


def _history_dialog_inner(fig):
    big = go.Figure(fig)
    big.update_layout(height=560 + (fig.layout.height or 300) - 300)
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


def render_history(sel_portfolios, display_ccy, native, compact, right_extra, market_rows=None):
    """Graficul istoric cu alegerea perioadei; right_extra() se randeaza la final in coloana din dreapta.
    market_rows: pozitiile afisate; sub axa X apar intervalele in care sunt deschise bursele lor.
    Intoarce True daca graficul a fost afisat (altfel istoricul abia se aduna)."""
    portfolio_history = multi_history_records(sel_portfolios, display_ccy)
    if native and len(portfolio_history) < 2:
        portfolio_history = load_portfolio_history()
    if len(portfolio_history) < 2:
        st.caption(t("hist.accumulating"))
        return False
    history_df = pd.DataFrame(portfolio_history)
    history_df["x"] = history_df["ts"].fillna(history_df["date"]) if "ts" in history_df.columns else history_df["date"]
    # toate momentele in ora locala (vezi history_multi.to_local: punctele vechi in UTC, cele noi in ora locala)
    history_df["x"] = pd.to_datetime([to_local(v) for v in history_df["x"]])
    history_df = history_df.sort_values("x")
    _thr = 40.0 * float(_fx("EUR", display_ccy) or 1.0)
    if st.session_state.get("hist_hide_small", True):
        _f = history_df[history_df["invested"] >= _thr]
        if len(_f) >= 2:
            history_df = _f
    _first_all = history_df["x"].min()
    _ranges = list(HIST_RANGES)
    if mobile.compact():
        # pe telefon mai putine butoane, ca sa incapa pe un rand; perioadele lipsa trec la cea mai apropiata
        _ranges = list(HIST_RANGES_COMPACT)
        _cur = st.session_state.get("history_range")
        if _cur in _HIST_NEAR_COMPACT:
            st.session_state["history_range"] = _HIST_NEAR_COMPACT[_cur]
    if st.session_state.get("history_range") not in _ranges:
        _pref = st.session_state.get("_hist_range_pref")
        _pref = _HIST_NEAR_COMPACT.get(_pref, _pref) if mobile.compact() else _pref
        st.session_state["history_range"] = _pref if _pref in _ranges else "YTD"
    st.checkbox(t("hist.hide_small", thr=f"{_thr:,.0f} {display_ccy}"), value=True, key="hist_hide_small")
    _hc_left, _hc_right = st.columns(2)
    with _hc_left:
        range_choice = mobile.period_picker(
            "Perioadă", _ranges,
            key="history_range", label_visibility="collapsed",
        )
    st.session_state["_hist_range_pref"] = range_choice
    _now = pd.Timestamp(datetime.now())
    _deltas = {
        "3H": pd.Timedelta(hours=3), "1D": pd.Timedelta(days=1), "1W": pd.Timedelta(weeks=1),
        "1M": pd.Timedelta(days=30), "3M": pd.Timedelta(days=91), "6M": pd.Timedelta(days=182),
        "1Y": pd.Timedelta(days=365), "3Y": pd.Timedelta(days=3 * 365), "5Y": pd.Timedelta(days=5 * 365),
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
    if "hist_lines" not in st.session_state:
        _saved = load_pref("hist_lines")
        st.session_state["hist_lines"] = [k for k in _saved if k in LINES] if isinstance(_saved, list) else list(LINES)
    _nowl = pd.Timestamp(datetime.now())
    _first_local = pd.Timestamp(_first_all)
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
    with _hc_left:
        _lines = st.pills(t("hist.lines"), LINES, selection_mode="multi", key="hist_lines",
                          format_func=_line_label, label_visibility="collapsed")
    save_pref("hist_lines", list(_lines or []))
    _ys = {}
    if "value" in (_lines or []):
        _ys["value"] = history_df["market_value"].tolist()
    if "sp500" in (_lines or []):
        _sp = None
        _px = sp500_prices(range_choice, display_ccy)
        if _px is not None:
            _sp = benchmark.simulate(history_df["market_value"], history_df["invested"],
                                     benchmark.align(history_df["x"], _px))
        if _sp:
            _ys["sp500"] = _sp
        else:
            st.caption(t("hist.sp500_missing"))
    if "invested" in (_lines or []):
        _ys["invested"] = history_df["invested"].tolist()
    history_fig = go.Figure()
    for _k, _y in _ys.items():
        history_fig.add_trace(go.Scatter(
            x=history_df["x"], y=_y, name=t("hist.line." + _k), mode="lines",
            line=dict(color=_LINE_COLORS[_k], width=2.5, dash="dot" if _k == "invested" else None),
        ))
    history_fig.update_layout(
        title=f"{_tx('Valoare de piață în timp')} ({display_ccy})",
        height=300,
        margin=dict(l=10, r=10, t=60, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    if _ys:
        _all = [float(v) for _y in _ys.values() for v in _y]
        _lo, _hi = min(_all), max(_all)
        _pad = max((_hi - _lo) * 0.15, abs(_hi) * 0.0005)
        history_fig.update_yaxes(range=[_lo - _pad, _hi + _pad], tickformat=",.0f")
    # liniile se aleg din butoanele de deasupra (alegerea ramane salvata); legenda doar le numeste
    history_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, itemclick=False,
                                          itemdoubleclick=False), showlegend=bool(_ys))
    history_fig.update_layout(hovermode="x unified")
    history_fig.update_traces(hovertemplate="%{y:,.2f}")
    if privacy.hidden():
        # forma curbei ramane, valorile nu (fara axa Y si fara hover)
        history_fig.update_yaxes(showticklabels=False)
        history_fig.update_traces(hoverinfo="skip", hovertemplate=None)
    _x1 = pd.Timestamp(datetime.now())
    if range_choice == "YTD":
        _x0 = pd.Timestamp(_x1.year, 1, 1)
    elif range_choice == "Max":
        _x0 = history_df["x"].min()
    else:
        _x0 = _x1 - _deltas[range_choice]
    _x0 = min(_x0, history_df["x"].min())
    history_fig.update_xaxes(range=[_x0, _x1])
    if market_rows is not None:
        try:
            from market_hours_ui import add_market_bands
            history_fig.update_layout(height=add_market_bands(history_fig, market_rows, _x0, _x1, 300))
        except Exception as _e:  # benzile sunt un plus: graficul ramane si fara ele
            st.caption(t("mh.bands_error", e=_e))
    if len(history_df) <= 40:
        history_fig.update_traces(mode="lines+markers", marker=dict(size=5))
    with _hc_left:
        if not _ys:
            # fara nicio linie graficul ar fi gol, cu axe fara sens: cerem alegerea unei linii
            # card turcoaz in stilul alertelor (fara galbenul st.warning, la cererea utilizatorului)
            st.markdown('<div style="background:rgba(34,184,207,0.22);border-left:4px solid #22b8cf;'
                        'border-radius:0.5rem;padding:0.75rem 1rem;line-height:1.5">💡 %s</div>'
                        % html.escape(t("hist.no_lines")), unsafe_allow_html=True)
            return True
        mobile.plotly_chart(history_fig, width="stretch", key="portfolio_history_chart")
        if not compact and "sp500" in _ys:
            st.caption(t("hist.sp500_help", ccy=display_ccy))
        _enlarge = not compact and st.button(t("hist.enlarge"), key="history_enlarge")
    if _enlarge:
        _history_dialog(history_fig)
    return True
