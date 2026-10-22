"""Tab-ul Comparatie din pagina principala."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import mobile

import compare
from core import CHART_PERIODS, load_json_file, QUALITY_CACHE_FILE
from i18n import t
from yf_compat import yf, YFINANCE_AVAILABLE

# paleta categoriala, in ordine fixa; culoarea urmeaza simbolul, nu pozitia lui in lista
COLORS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")
LABEL_GAP = 0.055  # distanta minima intre etichete, ca fractie din intervalul vertical (~un rand de text)
_G2D = {"3H": "1Z", "1D": "1Z", "1W": "1S", "1M": "1L", "1Y": "1A", "YTD": "YTD", "Max": "Max"}


@st.cache_data(ttl=21600, show_spinner=False)
def get_info(symbol):
    if not YFINANCE_AVAILABLE:
        return {}
    try:
        return compare.fundamentals(yf.Ticker(symbol).info or {})
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def get_closes(symbols, period, interval):
    if not YFINANCE_AVAILABLE or not symbols:
        return pd.DataFrame()
    try:
        df = yf.download(list(symbols), period=period, interval=interval, auto_adjust=True,
                         progress=False, group_by="column", threads=True)
        return compare.closes_from_download(df, list(symbols))
    except Exception:
        return pd.DataFrame()


def _options(vdf):
    """Pozitiile si watchlist-ul: {simbol Yahoo: (eticheta, ticker intern sau None)}."""
    from watchlist import load_watchlist
    opts = {}
    if vdf is not None and not vdf.empty:
        for r in vdf.to_dict("records"):
            sym = r.get("yahoo_symbol")
            if sym and sym not in opts:
                opts[sym] = ("%s (%s)" % (r.get("name") or sym, sym), r.get("ticker"))
    for w in load_watchlist():
        sym = w.get("symbol") if isinstance(w, dict) else w
        if sym and sym not in opts:
            opts[sym] = ("👁️ " + sym, None)
    return opts


def _scores(symbol, ticker, kind):
    """Scorurile din cache-ul pozitiilor sau al watchlist-ului; altfel calculate pe loc (doar actiuni)."""
    q = load_json_file(QUALITY_CACHE_FILE, {}).get(ticker) if ticker else None
    if q:
        def ok(v, c):
            return v if v is not None and (c or 0) >= 50 else None
        return ok(q.get("total"), q.get("coverage")), ok(q.get("risk_total"), q.get("risk_coverage")), \
            ok(q.get("div_total"), q.get("div_coverage"))
    if kind == "etf":
        return None, None, None
    from detail_view import get_dividend_score, get_quality_score, get_risk
    qr, _ = get_quality_score(symbol)
    rr, _ = get_risk(symbol)
    dr, _ = get_dividend_score(symbol)

    def total(r):
        return r.get("total") if r and (r.get("coverage") or 0) >= 50 else None
    return total(qr), total(rr), total(dr)


def _chart(norm, labels, colors):
    fig = go.Figure()
    for sym in norm.columns:
        s = norm[sym].dropna()
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, mode="lines", name=labels[sym], line={"color": colors[sym], "width": 2},
            hovertemplate=labels[sym] + ": %{y:+.1f}%<extra></extra>"))
        fig.add_trace(go.Scatter(
            x=[s.index[-1]], y=[s.iloc[-1]], mode="markers", marker={"color": colors[sym], "size": 8},
            showlegend=False, hoverinfo="skip"))
    # etichete directe la capatul liniilor, ca identitatea sa nu depinda doar de culoare;
    # cele prea apropiate se departeaza pe verticala (punctul ramane la valoarea reala)
    ends = {sym: float(norm[sym].dropna().iloc[-1]) for sym in norm.columns if not norm[sym].dropna().empty}
    y_min, y_max = min(float(norm.min().min()), 0.0), max(float(norm.max().max()), 0.0)
    gap = max(y_max - y_min, 1e-6) * LABEL_GAP
    placed = compare.spread_labels(ends, gap)
    # axa include si etichetele impinse peste capete, ca sa nu fie taiate
    fig.update_yaxes(range=[min(y_min, *placed.values()) - gap, max(y_max, *placed.values()) + gap])
    for sym, y in placed.items():
        last_x = norm[sym].dropna().index[-1]
        fig.add_annotation(x=last_x, y=y, text=f"{sym} {ends[sym]:+.1f}%", showarrow=False,
                           xanchor="left", xshift=8, yanchor="middle")
    fig.add_hline(y=0, line={"color": "#9a9994", "width": 1})
    fig.update_layout(height=420, hovermode="x unified", margin={"l": 10, "r": 110, "t": 10, "b": 10},
                      yaxis={"ticksuffix": "%", "gridcolor": "rgba(154,153,148,0.2)"},
                      xaxis={"showgrid": False, "showspikes": True, "spikemode": "across", "spikethickness": 1},
                      legend={"orientation": "h", "y": -0.12})
    return fig


def _color_slots(symbols):
    """Fiecare simbol isi pastreaza slotul de culoare cat timp ramane selectat; unul nou ia primul slot liber."""
    slots = {s: i for s, i in st.session_state.get("cmp_colors", {}).items() if s in symbols}
    for s in symbols:
        if s not in slots:
            slots[s] = next(i for i in range(len(COLORS)) if i not in slots.values())
    st.session_state["cmp_colors"] = slots
    return slots


def _sector(name):
    if not name:
        return "n/a"
    label = t("ex.sector." + name)
    return name if label.startswith("ex.sector.") else label


def _pct(v):
    return f"{v:+.1f}%" if v is not None else "n/a"


def _fmt(v, d=1, suffix=""):
    return f"{v:,.{d}f}{suffix}" if v is not None else "n/a"


def _cap(v):
    if v is None:
        return "n/a"
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if v >= div:
            return f"{v / div:,.1f}{suf}"
    return f"{v:,.0f}"


def render_compare_tab(vdf):
    if not YFINANCE_AVAILABLE:
        st.info(t("cmp.no_yf"))
        return
    opts = _options(vdf)
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    # selectia si perioada stau in URL (?cmp=AAPL&cmp=KO&cmp_period=1A): refresh-ul si linkurile le pastreaza.
    # Cat timp tabul e inchis, widget-urile nu se randeaza; copia de rezerva le reface la revenire.
    for key in ("cmp", "cmp_period"):
        if key not in st.session_state and key not in st.query_params and st.session_state.get("_saved_" + key):
            st.session_state[key] = st.session_state["_saved_" + key]
    chosen = c1.multiselect(
        t("cmp.pick", n=compare.MAX_SYMBOLS), list(opts), key="cmp", max_selections=compare.MAX_SYMBOLS,
        accept_new_options=True, format_func=lambda s: opts[s][0] if s in opts else s,
        placeholder=t("cmp.placeholder"), bind="query-params")
    period = c2.segmented_control(
        t("dv.period"), list(CHART_PERIODS), key="cmp_period", bind="query-params",
        default=_G2D.get(st.session_state.get("_hist_range_pref", "YTD"), "YTD"),
        format_func=lambda k: t("dv.per." + k)) or "YTD"
    st.session_state["_saved_cmp"], st.session_state["_saved_cmp_period"] = list(chosen), period
    symbols = list(dict.fromkeys(compare.parse_symbols(" ".join(chosen))))
    if len(symbols) < 2:
        st.caption(t("cmp.hint"))
        return

    yf_period, yf_interval = CHART_PERIODS[period]
    with st.spinner(t("cmp.loading")):
        closes = get_closes(tuple(symbols), yf_period, yf_interval)
        infos = {s: get_info(s) for s in symbols}
    missing = [s for s in symbols if s not in closes.columns or closes[s].dropna().empty]
    if missing:
        st.warning(t("cmp.missing", s=", ".join(missing)))
    norm = compare.normalize(closes)
    labels = {s: (opts[s][0] if s in opts else (infos[s].get("name") or s)) for s in symbols}
    colors = {s: COLORS[slot] for s, slot in _color_slots(symbols).items()}
    if not norm.empty:
        mobile.plotly_chart(_chart(norm, labels, colors), width="stretch", key="cmp_chart")

    rows = []
    with st.spinner(t("cmp.scores")):
        for s in symbols:
            info = infos.get(s) or {}
            stats = compare.period_stats(closes[s] if s in closes.columns else None, yf_interval)
            q, r, d = _scores(s, opts[s][1] if s in opts else None, info.get("kind"))
            rows.append({
                t("cmp.col.symbol"): s,
                t("cmp.col.name"): info.get("name") or labels[s],
                t("cmp.col.return"): _pct(stats["return"]),
                t("cmp.col.volatility"): _fmt(stats["volatility"], 1, "%"),
                t("cmp.col.drawdown"): _fmt(stats["max_drawdown"], 1, "%"),
                t("cmp.col.quality"): _fmt(q, 0, "/100"),
                t("cmp.col.risk"): _fmt(r, 0, "/100"),
                t("cmp.col.dividend"): _fmt(d, 0, "/100"),
                t("cmp.col.pe"): _fmt(info.get("pe")),
                t("cmp.col.fpe"): _fmt(info.get("forward_pe")),
                t("cmp.col.yield"): _fmt(info.get("dividend_yield"), 2, "%"),
                t("cmp.col.target"): _pct(info.get("target_upside")),
                t("cmp.col.beta"): _fmt(info.get("beta"), 2),
                t("cmp.col.cap"): _cap(info.get("market_cap")),
                t("cmp.col.sector"): _sector(info.get("sector")),
                t("cmp.col.country"): info.get("country") or "n/a",
                t("cmp.col.ccy"): info.get("currency") or "n/a",
            })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(t("cmp.note"))
