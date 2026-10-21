from yf_compat import yf, YFINANCE_AVAILABLE
import streamlit as st
from i18n import t as tr, lang as _lang, x as _x
import requests
import pandas as pd
import numpy as np
import base64
import os
import json
import time
import threading
import tempfile
from datetime import datetime
from urllib.parse import quote
import plotly.graph_objects as go
import plotly.express as px

from checklist import build_checklist
from descriptions import TABLE_HELP, checklist_tooltip, indicator_tooltip, score_tooltip
from core import CHART_PERIODS, RECOMMENDATION_LABELS, SECTOR_TYPICAL_RANGES, load_config, load_notes, load_ticker_map, save_note, save_ticker_map
from etf import ETF_INDICATORS, compute_etf_score, extract_etf_metrics, get_instrument
from gauges import make_gauge
from holdings_ui import render_holdings_section, target_portfolios
from xtb_positions import xtb_rows
from risk import RISK_INDICATORS, compute_risk, extract_risk_metrics
from valuation import red_count, valuation_rows
from scoring import INDICATORS, compute_score, extract_metrics
from dividend_score import PILLARS, compute_dividend_score, extract_dividend_metrics
from position_alerts_ui import cached_holdings, render_quick_price_alert
from analysts_ui import render_analyst_section
from userctx import current_user
from t212_api import fetch_account_currency, fetch_order_history_for_ticker
from yahoo import fetch_benchmark_return, fetch_price_chart_history, fetch_sector_etf_reference, fetch_yahoo_analysis, fetch_yahoo_currency_hint, guess_yahoo_symbol
from xtb_positions import xtb_holdings



@st.cache_data(ttl=21600)
def get_quality_score(yahoo_symbol):
    if not YFINANCE_AVAILABLE:
        return None, {}
    try:
        tk = yf.Ticker(yahoo_symbol)
        metrics, notes = extract_metrics(tk)
        result = compute_score(metrics)
        return result, notes
    except Exception:
        return None, {}


@st.cache_data(ttl=21600)
def get_dividend_score(yahoo_symbol):
    """(rezultat, plateste) - rezultat None daca nu s-au putut citi datele."""
    if not YFINANCE_AVAILABLE:
        return None, False
    try:
        metrics, pays = extract_dividend_metrics(yf.Ticker(yahoo_symbol))
        return (compute_dividend_score(metrics) if pays else None), pays
    except Exception:
        return None, True


def _render_dividend_score(yahoo_symbol, is_etf):
    st.divider()
    st.subheader(tr("dv.div_title"))
    if is_etf:
        st.info(tr("dv.div_etf"))
        return
    result, pays = get_dividend_score(yahoo_symbol)
    if not pays:
        st.info(tr("dv.div_none"))
        return
    if not result:
        st.info(tr("dv.div_no_data"))
        return
    st.metric(tr("dv.div_score"), f"{result['total']:.0f}/100", _x(result["rating"]), delta_color="off",
              help=tr("help.div_score"))
    cols = st.columns(len(PILLARS))
    for c, p in zip(cols, PILLARS):
        v = result["pillars"].get(p)
        c.metric(tr("dv.div_pillar." + p), f"{v:.0f}/100" if v is not None else "n/a")
    st.dataframe(pd.DataFrame([{
        tr("dv.div_col.indicator"): tr("dv.div_ind." + r["key"]),
        tr("dv.div_col.value"): round(r["value"], 1) if r["value"] is not None else None,
        tr("dv.div_col.target"): r["target"],
        tr("dv.div_col.red_flag"): r["red_flag"],
        tr("dv.div_col.score"): f"{r['score'] * 100:.0f}/100" if r["score"] is not None else "n/a",
    } for r in result["rows"]]), hide_index=True, width="stretch")
    st.caption(tr("dv.div_coverage", c=f"{result['coverage']:.0f}") + " " + tr("dv.div_hint"))


@st.cache_data(ttl=21600)
def get_risk(yahoo_symbol):
    if not YFINANCE_AVAILABLE:
        return None, {}
    try:
        tk = yf.Ticker(yahoo_symbol)
        quality_metrics, _ = extract_metrics(tk)
        metrics, notes = extract_risk_metrics(tk, quality_metrics)
        result = compute_risk(metrics)
        return result, notes
    except Exception:
        return None, {}


@st.cache_data(ttl=21600)
def get_etf_score(isin, yahoo_symbol):
    try:
        metrics, labels, notes = extract_etf_metrics(isin, yahoo_symbol)
        result = compute_etf_score(metrics)
        return result, labels, notes
    except Exception:
        return None, {}, {}


def scroll_page_to_top():
    """Forțează scroll la (0,0) — cu delay, ca să apuce layout-ul să se așeze după rerun,
    și țintind mai multe containere posibile, pentru robustețe între versiuni Streamlit."""
    st.html(
        """
        <script>
        // nonce: """ + str(time.time()) + """
        setTimeout(function() {
            var doc = window.parent.document;
            window.parent.scrollTo(0, 0);
            doc.documentElement.scrollTop = 0;
            doc.body.scrollTop = 0;
            ['section.main', '[data-testid="stAppViewContainer"]', '[data-testid="stMain"]'].forEach(function(sel) {
                var el = doc.querySelector(sel);
                if (el) { el.scrollTop = 0; }
            });
        }, 150);
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _render_price_chart_inner(ticker, yahoo_symbol, fill_date, avg_price_t212):
    st.subheader(tr("dv.chart_title"))
    _pkey = f"chart_period_{ticker}"
    if _pkey not in st.session_state:
        _g2d = {"3H": "1Z", "1D": "1Z", "1W": "1S", "1M": "1L", "1Y": "1A", "YTD": "YTD", "Max": "Max"}
        st.session_state[_pkey] = _g2d.get(st.session_state.get("_hist_range_pref", "YTD"), "YTD")
    period_choice = st.radio(
        tr("dv.period"), list(CHART_PERIODS.keys()), horizontal=True, key=_pkey,
        format_func=lambda _k: tr("dv.per." + _k),
    )
    yf_period, yf_interval = CHART_PERIODS[period_choice]
    hist, err = fetch_price_chart_history(yahoo_symbol, yf_period, yf_interval)
    if err:
        st.warning(err)
        return

    if fetch_yahoo_currency_hint(yahoo_symbol) == "GBp":
        hist = hist.copy()
        hist["Close"] = hist["Close"] / 100  # Yahoo dă LSE în pence — normalizăm la GBP

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name=yahoo_symbol, line=dict(width=2)))

    if fill_date is not None:
        try:
            fill_date_naive = fill_date.replace(tzinfo=None)
            hist_dates = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
            if hist_dates.min() <= fill_date_naive <= hist_dates.max():
                diffs = abs((hist_dates - fill_date_naive).total_seconds())
                pos = int(np.argmin(diffs.values)) if hasattr(diffs, "values") else int(diffs.argmin())
                marker_x = hist.index[pos]
                marker_y = hist["Close"].iloc[pos]
                fig.add_trace(go.Scatter(
                    x=[marker_x], y=[marker_y], mode="markers+text", name=tr("dv.bought"),
                    marker=dict(size=12, color="orange", symbol="star"),
                    text=[tr("dv.bought_here")], textposition="top center",
                ))
        except Exception:
            pass

    fig.update_layout(
        height=400, margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False, xaxis_title=None, yaxis_title=None,
        template="plotly_dark",
    )
    st.plotly_chart(fig, width="stretch", key=f"price_chart_{ticker}")
    _pc_big = st.button(tr("hist.enlarge"), key=f"price_enlarge_{ticker}")
    if _pc_big:
        _show_big_price(fig, ticker)
    st.caption(
        tr("dv.buy_marker_note")
    )


def render_price_chart(ticker, yahoo_symbol, fill_date, avg_price_t212, right_renderer=None):
    left, right = st.columns(2)
    if right_renderer:
        with right:
            right_renderer()
    with left:
        _render_price_chart_inner(ticker, yahoo_symbol, fill_date, avg_price_t212)


def _show_big_price(fig, ticker):
    @st.dialog(tr("dv.chart_title"), width="large")
    def _dlg():
        big = go.Figure(fig)
        big.update_layout(height=560)
        st.plotly_chart(big, width="stretch", key=f"price_chart_big_{ticker}")
    _dlg()


def _xtb_positive_amount(value):
    if value is None or pd.isna(value):
        return None

    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def render_detail_view(position_row, total_portfolio_value, api_key_id, api_secret):
    ticker = position_row["ticker"]
    name = position_row.get("name", ticker)
    instr_ccy = position_row.get("currencyCode", "")

    if st.session_state.pop("scroll_to_top_detail", False):
        scroll_page_to_top()

    _HEADER_CSS = """<style>
[data-testid="stMainBlockContainer"], .block-container {padding-top: 0.5rem !important;}
[data-testid="stHeader"] {background: transparent !important; pointer-events: none !important; z-index: 100 !important;}
[data-testid="stHeader"] * {pointer-events: none !important;}
.st-key-detail_header {
    position: sticky; top: 0; z-index: 999;
    background: var(--background-color, #0e1117);
    padding: 0.35rem 0 0.25rem 0;
    min-height: 3.6rem;
    border-bottom: 1px solid rgba(250,250,250,0.12);
}
[data-testid="stLayoutWrapper"]:has(> .st-key-detail_header),
[data-testid="stElementContainer"]:has(> .st-key-detail_header) {
    position: sticky; top: 0; z-index: 999;
}
.st-key-detail_header [data-testid="stMarkdownContainer"] h2 {
    font-size: 2.2rem; line-height: 1.2; margin: 0; padding: 0;
}
@keyframes dv-shrink {from {font-size: 2.2rem;} to {font-size: 1.3rem;}}
@supports (animation-timeline: scroll()) {
    .st-key-detail_header [data-testid="stMarkdownContainer"] h2 {
        animation: dv-shrink linear both;
        animation-timeline: scroll(nearest);
        animation-range: 0px 140px;
    }
}
</style>"""

    with st.container(key="detail_header"):
        st.markdown(_HEADER_CSS, unsafe_allow_html=True)
        mapping = load_ticker_map()
        default_symbol = mapping.get(ticker, guess_yahoo_symbol(ticker))
        col_back, col_title, col_sym, col_save = st.columns([2, 6, 3, 2], vertical_alignment="center")
        with col_back:
            if st.button(tr("dv.back")):
                st.session_state.pop("selected_ticker", None)
                st.session_state["scroll_to_top_main"] = True
                st.session_state["table_nonce"] = st.session_state.get("table_nonce", 0) + 1
                st.rerun()
        with col_title:
            st.markdown(f"## 🔍 {name} ({ticker})")
        with col_sym:
            yahoo_symbol = st.text_input(
                tr("dv.map_label"),
                value=default_symbol, key=f"yahoo_sym_{ticker}",
                label_visibility="collapsed", help=tr("dv.map_label"),
            )
        with col_save:
            if st.button(tr("dv.save_map"), key=f"save_map_{ticker}"):
                mapping[ticker] = yahoo_symbol
                save_ticker_map(mapping)
                st.toast(tr("dv.saved"))

    # preîncărcare în paralel a apelurilor Yahoo lente (rezultatele intră în st.cache_data)
    import threading as _th
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
        _ctx = get_script_run_ctx()
    except Exception:
        add_script_run_ctx, _ctx = None, None

    def _prefetch(fn, *args):
        def _run():
            try:
                fn(*args)
            except Exception:
                pass
        th = _th.Thread(target=_run, daemon=True)
        if add_script_run_ctx and _ctx:
            add_script_run_ctx(th, _ctx)
        th.start()

    _prefetch(fetch_yahoo_analysis, yahoo_symbol)
    _prefetch(get_risk, yahoo_symbol)
    _prefetch(fetch_yahoo_currency_hint, yahoo_symbol)

    zile_detinut = None
    fill_date = None
    _fill_src = position_row.get("initialFillDate")
    if not _fill_src and position_row.get("watchlist"):
        _cands = [
            r.get("initialFillDate") for r in xtb_rows()
            if r.get("initialFillDate") and (r.get("ticker") == ticker or r.get("yahoo_symbol") == yahoo_symbol)
        ]
        _fill_src = min(_cands) if _cands else None
    if _fill_src:
        try:
            fill_date = datetime.fromisoformat(_fill_src.replace("Z", "+00:00"))
            zile_detinut = (datetime.now(fill_date.tzinfo) - fill_date).days
        except Exception:
            zile_detinut = None

    data, err = None, None
    if YFINANCE_AVAILABLE:
        with st.spinner(f"Interogare Yahoo Finance pentru {yahoo_symbol}..."):
            data, err = fetch_yahoo_analysis(yahoo_symbol)

    if data and data.get("business_summary"):
        _meta = [x for x in (data.get("long_name"), " / ".join(y for y in (data.get("sector"), data.get("industry")) if y)) if x]
        st.caption(" · ".join(_meta))
    elif err:
        st.warning(err)

    is_watch = bool(position_row.get("watchlist"))
    account_currency = None
    if not is_watch:
        account_currency, _ = fetch_account_currency(api_key_id, api_secret)
        account_currency = account_currency or "?"

    _PANEL_CSS = """<style>
.st-key-holdings_panel [data-testid="stMetricValue"] {font-size:1.15rem; line-height:1.25;}
.st-key-holdings_panel [data-testid="stMetricLabel"] p {font-size:0.72rem;}
.st-key-holdings_panel [data-testid="stMetricDelta"] {font-size:0.7rem;}
.st-key-holdings_panel [data-testid="stVerticalBlock"] {gap:0.3rem;}
</style>"""

    def _holdings_panel():
        with st.container(key="holdings_panel"):
            st.markdown(_PANEL_CSS, unsafe_allow_html=True)
            render_holdings_section(ticker, position_row, yahoo_symbol, total_portfolio_value, zile_detinut, account_currency, is_watch)
            if data and (data.get("next_dividend_date") or data.get("ex_dividend_date")):
                st.caption(
                    f"💰 Următorul dividend estimat: **{data.get('next_dividend_date') or 'n/a'}** "
                    f"(data ex-dividend: {data.get('ex_dividend_date') or 'n/a'})"
                )

    if YFINANCE_AVAILABLE and not err:
        render_price_chart(ticker, yahoo_symbol, fill_date, position_row.get('averagePrice'),
                           right_renderer=_holdings_panel)
    else:
        _holdings_panel()
    if data and data.get("business_summary"):
        with st.expander(tr("dv.description"), expanded=False):
            st.write(data["business_summary"])

    is_etf = False
    checklist_quality_total = None
    checklist_quality_coverage = None
    checklist_quality_rating = None
    checklist_risk_total = None
    checklist_risk_coverage = None
    checklist_valuation_red = None
    checklist_valuation_usable = None
    checklist_drawdown_52w = None
    checklist_price = None
    checklist_sma200 = None
    checklist_ret_3m = None
    _held = cached_holdings(current_user()).get(ticker)
    if _held:
        render_quick_price_alert(ticker, _held.get("name"), _held.get("price"), _held.get("ccy"))
    st.markdown("---")

    # --- scor de calitate ---
    if is_watch:
        isin = position_row.get("isin")
        is_etf = (position_row.get("type") == "ETF") if position_row.get("type") else (isin is not None)
    else:
        instr = get_instrument(ticker)
        isin = instr.get("isin") if instr is not None else None
        is_etf = instr is not None and instr.get("type") == "ETF"

    if is_etf:
        st.subheader(tr("dv.etf_score_title"))
        if not isin:
            st.info(tr("dv.etf_no_isin"))
        else:
            etf_result, etf_labels, etf_notes = get_etf_score(isin, yahoo_symbol)
            if not etf_result:
                st.info(tr("dv.etf_no_data"))
            else:
                total_val = etf_result.get("total", 0.0)
                rating_val = etf_result.get("rating", "n/a")
                coverage_val = etf_result.get("coverage", 0.0)
                checklist_quality_total = total_val
                checklist_quality_coverage = coverage_val
                checklist_quality_rating = rating_val
                st.metric(tr("dv.etf_score"), f"{total_val:.1f} / 100", rating_val, delta_color="off", help=score_tooltip("etf"))

                caption_parts = [f"Calculat pe {coverage_val:.0f}% din ponderi."]
                if etf_notes:
                    notes_str = "; ".join(f"{k}: {v}" for k, v in etf_notes.items())
                    caption_parts.append(f"Note: {notes_str}")
                st.caption(" · ".join(caption_parts))

                def caption_value(v):
                    if v is None or pd.isna(v):
                        return None
                    if isinstance(v, bool):
                        return "Da" if v else "Nu"
                    return str(v)

                label_parts = []
                for label, key in [
                    ("ISIN", "isin"),
                    ("Domiciliu", "domiciliu"),
                    ("Acc/Dist", "distributie"),
                    ("Hedged", "hedged"),
                    ("Securities lending", "securities_lending"),
                    ("Replicare", "replicare"),
                ]:
                    value = caption_value(etf_labels.get(key))
                    if value is not None:
                        label_parts.append(f"{label}: {value}")

                if label_parts:
                    st.caption(" · ".join(label_parts))

                etf_hib_by_key = {ind["key"]: ind["higher_is_better"] for ind in ETF_INDICATORS}
                rows = etf_result.get("rows", [])
                for chunk_start in range(0, len(rows), 3):
                    cols = st.columns(3)
                    for i, r in enumerate(rows[chunk_start:chunk_start + 3]):
                        with cols[i]:
                            r_key = r["key"]
                            r_label = r["label"]
                            if r["value"] is None or pd.isna(r["value"]):
                                st.caption(f"{r_label}: n/a")
                                continue

                            fig_g = make_gauge(
                                label=r_label,
                                value=r["value"],
                                target=r["target"],
                                red_flag=r["red_flag"],
                                higher_is_better=etf_hib_by_key.get(r_key, True),
                                show_label=False,
                            )
                            if fig_g is not None:
                                st.markdown(f"**{r_label}**", help=indicator_tooltip("etf", r_key))
                                st.plotly_chart(fig_g, width="stretch", key=f"egauge_{ticker}_{r_key}")
                            else:
                                st.caption(f"{r_label}: n/a")

                with st.expander(tr("dv.indicator_details")):
                    def fmt_val(v, decimals=2):
                        if v is None or pd.isna(v):
                            return "n/a"
                        return f"{v:.{decimals}f}"

                    table_rows = []
                    for r in rows:
                        table_rows.append({
                            "Indicator": r["label"],
                            "Valoare": fmt_val(r["value"]),
                            "Target": fmt_val(r["target"]),
                            "Red Flag": fmt_val(r["red_flag"]),
                            "Pondere": f"{r['weight']}%",
                            "Scor (0-1)": fmt_val(r["score"]),
                            "Puncte": fmt_val(r["points"]),
                        })
                    table_df = pd.DataFrame(table_rows)
                    st.dataframe(
                        table_df,
                        hide_index=True,
                        width="stretch",
                        column_config={
                            name: st.column_config.Column(name, help=text)
                            for name, text in TABLE_HELP.items()
                            if name in table_df.columns
                        },
                    )

                row_by_key = {r["key"]: r for r in rows}
                replication_value = row_by_key.get("replication", {}).get("value")
                if replication_value == 0:
                    st.warning(tr("dv.etf_swap"))

                domicile = etf_labels.get("domiciliu")
                if domicile and str(domicile).strip().lower() not in {"ireland", "luxembourg"}:
                    st.warning(tr("dv.etf_domicile", d=domicile))

                ter_value = row_by_key.get("ter", {}).get("value")
                if ter_value is not None and not pd.isna(ter_value) and ter_value > 0.60:
                    st.warning(tr("dv.etf_ter", v=f"{ter_value:.2f}"))
    else:
        st.subheader(tr("dv.quality_title"))
        if not YFINANCE_AVAILABLE:
            st.info(tr("dv.no_yf_quality"))
        else:
            score_result, score_notes = get_quality_score(yahoo_symbol)
            if not score_result:
                st.info(tr("dv.quality_no_data"))
            else:
                total_val = score_result.get("total", 0.0)
                rating_val = score_result.get("rating", "n/a")
                coverage_val = score_result.get("coverage", 0.0)
                checklist_quality_total = total_val
                checklist_quality_coverage = coverage_val
                checklist_quality_rating = rating_val
                st.metric(tr("dv.quality_score"), f"{total_val:.1f} / 100", rating_val, delta_color="off", help=score_tooltip("quality"))

                caption_parts = [f"Calculat pe {coverage_val:.0f}% din ponderi."]
                if score_notes:
                    notes_str = "; ".join(f"{k}: {v}" for k, v in score_notes.items())
                    caption_parts.append(tr("dv.period_notes", n=notes_str))
                st.caption(" · ".join(caption_parts))

                hib_by_key = {ind["key"]: ind["higher_is_better"] for ind in INDICATORS}
                rows = score_result.get("rows", [])
                for chunk_start in range(0, len(rows), 4):
                    cols = st.columns(4)
                    for i, r in enumerate(rows[chunk_start:chunk_start + 4]):
                        with cols[i]:
                            r_key = r["key"]
                            r_label = r["label"]
                            fig_g = make_gauge(
                                label=r_label,
                                value=r["value"],
                                target=r["target"],
                                red_flag=r["red_flag"],
                                higher_is_better=hib_by_key.get(r_key, True),
                                show_label=False,
                            )
                            if fig_g is not None:
                                st.markdown(f"**{r_label}**", help=indicator_tooltip("quality", r_key))
                                st.plotly_chart(fig_g, width="stretch", key=f"gauge_{ticker}_{r_key}")
                            else:
                                st.caption(f"{r_label}: n/a")

                with st.expander(tr("dv.indicator_details")):
                    def fmt_val(v, decimals=2):
                        if v is None or pd.isna(v):
                            return "n/a"
                        return f"{v:.{decimals}f}"

                    table_rows = []
                    for r in score_result.get("rows", []):
                        table_rows.append({
                            "Indicator": r["label"],
                            "Valoare": fmt_val(r["value"]),
                            "Target": fmt_val(r["target"]),
                            "Red Flag": fmt_val(r["red_flag"]),
                            "Pondere": f"{r['weight']}%",
                            "Scor (0-1)": fmt_val(r["score"]),
                            "Puncte": fmt_val(r["points"]),
                        })
                    table_df = pd.DataFrame(table_rows)
                    st.dataframe(
                        table_df,
                        hide_index=True,
                        width="stretch",
                        column_config={
                            name: st.column_config.Column(name, help=text)
                            for name, text in TABLE_HELP.items()
                            if name in table_df.columns
                        },
                    )

    # --- risc ---
    st.divider()
    st.subheader(tr("dv.risk_title"))
    if not YFINANCE_AVAILABLE:
        st.info(tr("dv.no_yf_risk"))
    else:
        risk_result, risk_notes = get_risk(yahoo_symbol)
        if not risk_result:
            st.info(tr("dv.risk_no_data"))
        else:
            total_val = risk_result.get("total", 0.0)
            rating_val = risk_result.get("rating", "n/a")
            coverage_val = risk_result.get("coverage", 0.0)
            checklist_risk_total = total_val
            checklist_risk_coverage = coverage_val
            st.metric(tr("dv.risk_score"), f"{total_val:.1f} / 100", rating_val, delta_color="off", help=score_tooltip("risk"))

            caption_parts = [f"Calculat pe {coverage_val:.0f}% din ponderi."]
            if risk_notes:
                notes_str = "; ".join(f"{k}: {v}" for k, v in risk_notes.items())
                caption_parts.append(tr("dv.period_notes", n=notes_str))
            st.caption(" · ".join(caption_parts))
            st.caption(tr("dv.risk_hint"))

            risk_hib_by_key = {ind["key"]: ind["higher_is_better"] for ind in RISK_INDICATORS}
            rows = risk_result.get("rows", [])
            for chunk_start in range(0, len(rows), 3):
                cols = st.columns(3)
                for i, r in enumerate(rows[chunk_start:chunk_start + 3]):
                    with cols[i]:
                        r_key = r["key"]
                        r_label = r["label"]
                        if r["value"] is None or pd.isna(r["value"]):
                            st.caption(f"{r_label}: n/a")
                            continue

                        fig_g = make_gauge(
                            label=r_label,
                            value=r["value"],
                            target=r["target"],
                            red_flag=r["red_flag"],
                            higher_is_better=risk_hib_by_key.get(r_key, True),
                            show_label=False,
                        )
                        if fig_g is not None:
                            st.markdown(f"**{r_label}**", help=indicator_tooltip("risk", r_key))
                            st.plotly_chart(fig_g, width="stretch", key=f"rgauge_{ticker}_{r_key}")
                        else:
                            st.caption(f"{r_label}: n/a")

            if total_portfolio_value > 0 and position_row.get("valoare_curenta") is not None:
                st.caption(
                    f"Ponderea poziției în portofoliu: "
                    f"{position_row['valoare_curenta'] * position_row.get('fx_rate', 1.0) / total_portfolio_value * 100:.1f}%"
                )

    _render_dividend_score(yahoo_symbol, is_etf)

    st.divider()
    checklist_box = st.container()

    def _render_orders():
        if not is_watch:
            st.markdown("---")

            # --- istoricul tranzacțiilor ---
            st.subheader(tr("dv.orders_title"))
            disk_cfg = load_config()
            orders, orders_err = fetch_order_history_for_ticker(disk_cfg.get("api_key_id"), disk_cfg.get("api_secret"), ticker)
            if orders_err:
                st.warning(orders_err)
            elif not orders:
                st.info(tr("dv.no_orders"))
            else:
                def normalize_order(o):
                    # T212 a avut două forme de schemă pentru acest endpoint — încercăm ambele.
                    fill = o.get("fill", {}) or {}
                    wallet = fill.get("walletImpact", {}) or {}
                    return {
                        "Data execuției": o.get("dateExecuted") or fill.get("filledAt") or o.get("dateCreated"),
                        "Cantitate": o.get("filledQuantity", fill.get("quantity")),
                        f"Preț ({instr_ccy})": o.get("fillPrice", fill.get("price")),
                        f"Cost ({account_currency})": o.get("fillCost", wallet.get("netValue")),
                        "Status": o.get("status") or fill.get("type"),
                    }

                orders_df = pd.DataFrame([normalize_order(o) for o in orders])
                qty_col = "Cantitate"
                if qty_col in orders_df.columns:
                    orders_df.insert(1, "Tip", orders_df[qty_col].apply(lambda q: "Cumpărare" if (q or 0) > 0 else "Vânzare"))
                if orders_df.drop(columns=["Tip"], errors="ignore").isna().all(axis=None):
                    st.warning("Am primit date de la T212, dar niciun câmp cunoscut nu s-a potrivit — structura răspunsului "
                               "diferă de ce am prevăzut. Iată datele brute:")
                    st.json(orders[:5])
                else:
                    _show_df = orders_df
                    if _lang() == "EN":
                        _show_df = orders_df.copy()
                        if "Tip" in _show_df.columns:
                            _show_df["Tip"] = _show_df["Tip"].map(_x)
                        _show_df = _show_df.rename(columns={
                            c: (_x(c) if not c.startswith(("Preț (", "Cost (")) else c.replace("Preț (", "Price (", 1))
                            for c in _show_df.columns})
                    st.dataframe(_show_df, width="stretch", hide_index=True)


    st.markdown("---")

    # --- comparație cu piața ---
    if not is_watch:
        st.subheader(tr("dv.perf_title"))
    if is_watch:
        pass
    elif not YFINANCE_AVAILABLE:
        st.caption(tr("dv.needs_yf"))
    elif zile_detinut is None or fill_date is None:
        st.info(tr("dv.no_fill_date"))
    else:
        col_bench, _ = st.columns([2, 3])
        with col_bench:
            benchmark_symbol = st.text_input(
                tr("dv.bench_index"), value="^SP500TR", key=f"bench_{ticker}",
                help="^SP500TR = S&P 500 Total Return (include dividende reinvestite).",
            )

        bench_total, bench_err = fetch_benchmark_return(benchmark_symbol, fill_date.strftime("%Y-%m-%d"))
        position_total = position_row.get("randament_total_%", 0.0)

        if bench_err:
            st.warning(bench_err)
        else:
            delta = position_total - bench_total
            b1, b2, b3 = st.columns(3)
            b1.metric(tr("dv.your_return"), f"{position_total:+.2f}%")
            b2.metric(tr("dv.bench_period", sym=benchmark_symbol), f"{bench_total:+.2f}%")
            b3.metric(tr("dv.difference"), f"{delta:+.2f} pp")
            if delta > 0:
                st.success(tr("dv.beat", sym=benchmark_symbol, d=f"{delta:+.2f}"))
            else:
                st.error(tr("dv.under", sym=benchmark_symbol, d=f"{abs(delta):.2f}"))

    st.markdown("---")

    if not YFINANCE_AVAILABLE:
        st.warning(tr("dv.no_yf_installed"))
        _render_orders()
        return
    if err or not data:
        st.info(tr("dv.fix_symbol"))
        _render_orders()
        return

    sector = data.get("sector")
    sector_ref = fetch_sector_etf_reference(sector) if sector else None
    sector_typical = SECTOR_TYPICAL_RANGES.get(sector) if sector else None

    def sector_help(base_text, metric_key):
        extra = ""
        if sector_ref and sector_ref.get(metric_key) is not None:
            extra += f" · ETF sector ({sector_ref['etf_symbol']}): {sector_ref[metric_key]:.2f}."
        if sector_typical:
            label_map = {"pe": "pe", "pb": "pb"}
            k = label_map.get(metric_key)
            if k and sector_typical.get(k):
                extra += f" Reper uzual sector (aproximativ, static): {sector_typical[k]}."
        return base_text + extra

    is_etf_page = is_etf

    # --- valuation fundamental ---
    if not is_etf_page:
        st.subheader(tr("dv.valuation_title"))
        v1, v2, v3, v4, v5 = st.columns(5)
        v1.metric(
            "P/E (trailing)", f"{data['trailing_pe']:.2f}" if data['trailing_pe'] is not None else "n/a",
            help=sector_help(
                "Preț / profit pe acțiune din ultimele 12 luni. Arată de câți ani de profit curent ai nevoie ca "
                "să-ți recuperezi investiția.", "pe",
            ),
        )
        v2.metric(
            "P/E (forward)", f"{data['forward_pe']:.2f}" if data['forward_pe'] is not None else "n/a",
            help="Ca P/E trailing, dar cu profitul estimat pentru anul viitor. Mai mic decât trailing = piața "
                 "așteaptă creștere a profitului; mai mare = așteaptă scădere.",
        )
        v3.metric(
            "P/B", f"{data['price_to_book']:.2f}" if data['price_to_book'] is not None else "n/a",
            help=sector_help("Preț / valoare contabilă pe acțiune. Sub 1 poate însemna preț sub 'valoarea din carte'.", "pb"),
        )
        v4.metric(
            "P/S", f"{data['price_to_sales']:.2f}" if data['price_to_sales'] is not None else "n/a",
            help="Preț / vânzări pe acțiune. Util mai ales pentru companii încă neprofitabile, unde P/E nu are sens "
                 f"(reper uzual sector, aproximativ: {sector_typical.get('ps') if sector_typical else 'n/a'}).",
        )
        v5.metric(
            "EV/EBITDA", f"{data['ev_to_ebitda']:.2f}" if data['ev_to_ebitda'] is not None else "n/a",
            help="Valoare firmă (capitalizare + datorii - cash) / EBITDA. Compară companii cu structuri de capital "
                 f"diferite mai corect decât P/E (reper uzual sector: {sector_typical.get('ev_ebitda') if sector_typical else 'n/a'}).",
        )

        v6, v7, v8 = st.columns(3)
        v6.metric(
            "PEG", f"{data['peg_ratio']:.2f}" if data['peg_ratio'] is not None else "n/a",
            help="P/E împărțit la rata de creștere estimată a profitului. Sub 1 = potențial subevaluată relativ la creștere.",
        )
        div_y = data['dividend_yield_pct']
        v7.metric(
            "Dividend yield", f"{div_y:.2f}%" if div_y else "n/a",
            help="Dividendul anual ca procent din prețul curent. 2-4% moderat, peste 5-6% generos dar verifică sustenabilitatea.",
        )
        if data.get("market_cap"):
            v8.metric(
                "Capitalizare de piață", f"{data['market_cap']:,.0f} {data.get('currency', '')}",
                help="Nu am o sursă gratuită fiabilă pentru 'media capitalizării pe industrie' — depinde enorm de "
                     "câte companii mari/mici sunt incluse în comparație, deci nu o afișez ca reper aici.",
            )

        valuation_values = {
            "pe": data["trailing_pe"],
            "pe_fwd": data["forward_pe"],
            "peg": data["peg_ratio"],
            "ev_ebitda": data["ev_to_ebitda"],
            "ps": data["price_to_sales"],
            "pb": data["price_to_book"],
            "roe": data["roe_pct"],
        }
        valuation_gauge_rows, valuation_notes = valuation_rows(valuation_values)
        n_red, n_usable = red_count(valuation_gauge_rows)
        checklist_valuation_red = n_red
        checklist_valuation_usable = n_usable

        if n_usable > 0:
            for chunk_start in range(0, len(valuation_gauge_rows), 3):
                cols = st.columns(3)
                for i, row in enumerate(valuation_gauge_rows[chunk_start:chunk_start + 3]):
                    with cols[i]:
                        key = row["key"]
                        label = row["label"]
                        if not row["usable"]:
                            st.caption(f"{label}: n/a")
                            continue

                        fig_g = make_gauge(
                            label=label,
                            value=row["value"],
                            target=row["target"],
                            red_flag=row["red_flag"],
                            higher_is_better=False,
                            show_label=False,
                        )
                        if fig_g is not None:
                            st.markdown(f"**{label}**", help=indicator_tooltip("valuation", key))
                            st.plotly_chart(fig_g, width="stretch", key=f"vgauge_{ticker}_{key}")
                        else:
                            st.caption(f"{label}: n/a")

            st.caption(tr("dv.red_zone", r=n_red, n=n_usable))
            for note in valuation_notes:
                st.caption(note)

        st.markdown("---")

    # --- indicatori suplimentari (inspirați din stilul finviz) ---
    st.subheader(tr("dv.extra_title"))
    yccy = data.get("currency", "")
    x1, x2, x3, x4, x5 = st.columns(5)
    x1.metric("Enterprise Value", f"{data['enterprise_value']:,.0f} {yccy}" if data['enterprise_value'] else "n/a",
              help="Capitalizare de piață + datorii − numerar. Valoarea totală a firmei, indiferent cum e finanțată.")
    x2.metric("Book/sh", f"{data['book_value_per_share']:.2f} {yccy}" if data['book_value_per_share'] else "n/a",
              help="Valoare contabilă pe acțiune (active − datorii, împărțit la nr. de acțiuni).")
    x3.metric("Cash/sh", f"{data['cash_per_share']:.2f} {yccy}" if data['cash_per_share'] else "n/a",
              help="Numerar și echivalente pe acțiune.")
    x4.metric("Quick Ratio", f"{data['quick_ratio']:.2f}" if data['quick_ratio'] is not None else "n/a",
              help="Active lichide / datorii curente (fără stocuri). Peste 1 = poate acoperi datoriile pe termen scurt fără să vândă stocuri.")
    x5.metric("Current Ratio", f"{data['current_ratio']:.2f}" if data['current_ratio'] is not None else "n/a",
              help="Active curente / datorii curente. Reper: peste 1.5-2 e considerat confortabil, sub 1 poate semnala probleme de lichiditate.")

    x6, x7, x8, x9, x10 = st.columns(5)
    x6.metric("Debt/Equity", f"{data['debt_to_equity']:.2f}" if data['debt_to_equity'] is not None else "n/a",
              help="Datorii totale / capitaluri proprii. Reper orientativ: sub 1 conservator, peste 2 îndatorare ridicată — variază mult pe sector.")
    x7.metric("Payout Ratio", f"{data['payout_ratio_pct']:.1f}%" if data['payout_ratio_pct'] is not None else "n/a",
              help="Cât din profit se plătește ca dividend. Peste ~80-100% poate fi nesustenabil pe termen lung.")
    x8.metric("Short % Float", f"{data['short_pct_float_pct']:.2f}%" if data['short_pct_float_pct'] is not None else "n/a",
              help="Cât din acțiunile tranzacționabile sunt vândute short. Peste 10-15% poate însemna sentiment negativ puternic sau risc de 'short squeeze'.")
    x9.metric("Short Ratio", f"{data['short_ratio']:.2f}" if data['short_ratio'] is not None else "n/a",
              help="Zile necesare ca toate pozițiile short să fie acoperite, la volumul mediu de tranzacționare.")
    x10.metric("Rel Volume", f"{data['rel_volume']:.2f}x" if data['rel_volume'] is not None else "n/a",
               help="Volumul de azi față de volumul mediu. Peste 2x poate indica interes/mișcare neobișnuită.")

    x11, x12, x13 = st.columns(3)
    x11.metric("Avg Volume", f"{data['avg_volume']:,.0f}" if data['avg_volume'] is not None else "n/a")
    x12.metric("Prev Close", f"{data['prev_close']:.2f} {yccy}" if data['prev_close'] is not None else "n/a")
    x13.metric("Change %", f"{data['change_pct']:+.2f}%" if data['change_pct'] is not None else "n/a")

    st.markdown("---")

    # --- creștere & profitabilitate ---
    if not is_etf_page:
        st.subheader("📈 Creștere & Profitabilitate")
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("EPS (TTM)", f"{data['eps_ttm']:.2f}" if data['eps_ttm'] is not None else "n/a",
                  help="Profit net pe acțiune din ultimele 12 luni.")
        g2.metric("EPS estimat (anul viitor)", f"{data['eps_forward']:.2f}" if data['eps_forward'] is not None else "n/a",
                  help="Estimarea consensului de analiști pentru EPS anul viitor.")
        g3.metric("Creștere EPS estimată (5 ani)", f"{data['eps_5y_growth_pct']:+.1f}%/an" if data['eps_5y_growth_pct'] is not None else "n/a",
                  help="Estimare de consens a analiștilor pentru creșterea medie anuală a profitului pe următorii 5 ani — "
                       "best-effort, nu toate titlurile au acest câmp disponibil în Yahoo Finance.")
        g4.metric("Creștere EPS (YoY)", f"{data['earnings_growth_yoy_pct']:+.1f}%" if data['earnings_growth_yoy_pct'] is not None else "n/a",
                  help="Creșterea profitului față de aceeași perioadă anul trecut.")

        g5, g6, g7 = st.columns(3)
        g5.metric("Creștere vânzări (YoY)", f"{data['revenue_growth_yoy_pct']:+.1f}%" if data['revenue_growth_yoy_pct'] is not None else "n/a",
                  help="Creșterea veniturilor față de aceeași perioadă anul trecut.")
        g6.metric("Creștere vânzări (CAGR 3 ani)", f"{data['sales_growth_3y_cagr_pct']:+.1f}%/an" if data['sales_growth_3y_cagr_pct'] is not None else "n/a",
                  help="Rata anuală compusă de creștere a veniturilor pe ultimii ani disponibili în situațiile financiare anuale (până la 3 ani).")
        g7.metric("Marjă brută", f"{data['gross_margin_pct']:.1f}%" if data['gross_margin_pct'] is not None else "n/a",
                  help="Cât din venituri rămâne după costul direct al bunurilor/serviciilor vândute.")

        g8, g9, g10, g11 = st.columns(4)
        g8.metric("Marjă operațională", f"{data['operating_margin_pct']:.1f}%" if data['operating_margin_pct'] is not None else "n/a",
                  help="Profit operațional / venituri — eficiența operațiunilor de bază, înainte de dobânzi și taxe.")
        g9.metric("Marjă de profit netă", f"{data['profit_margin_pct']:.1f}%" if data['profit_margin_pct'] is not None else "n/a",
                  help="Profit net / venituri — cât din fiecare unitate vândută ajunge profit curat.")
        g10.metric("ROE", f"{data['roe_pct']:.1f}%" if data['roe_pct'] is not None else "n/a",
                   help="Return on Equity — profit net / capitaluri proprii. Reper: peste ~15% e considerat solid, dar variază pe sector.")
        g11.metric("ROA", f"{data['roa_pct']:.1f}%" if data['roa_pct'] is not None else "n/a",
                   help="Return on Assets — profit net / total active. Arată eficiența folosirii activelor pentru a genera profit "
                        "(ROIC nu e disponibil direct în Yahoo Finance fără calcule suplimentare din situațiile financiare — omis aici).")

        st.markdown("---")

    # --- proprietate ---
    if not is_etf_page:
        st.subheader("👤 Proprietate & Insideri")
        o1, o2, o3 = st.columns(3)
        o1.metric("Deținere insideri", f"{data['insider_ownership_pct']:.2f}%" if data['insider_ownership_pct'] is not None else "n/a",
                  help="Cât din companie e deținut de conducere/insideri. Deținere mare poate însemna aliniere de interese cu acționarii.")
        o2.metric("Deținere instituțională", f"{data['institutional_ownership_pct']:.2f}%" if data['institutional_ownership_pct'] is not None else "n/a",
                  help="Cât din companie e deținut de fonduri/instituții. Deținere mare = validare din partea investitorilor mari, dar și risc de mișcări bruște la ieșiri masive.")
        o3.metric("Tranzacții insideri (recent)", data.get("insider_tx_summary") or "n/a",
                  help=data.get("insider_tx_summary_full") or "Rezumatul ultimelor tranzacții raportate de conducere — cumpărările insiderilor sunt urmărite ca semnal de încredere.")

        st.markdown("---")

    # --- tehnic / momentum ---
    st.subheader("📉 Tehnic & Momentum")
    if data.get("price_clean_notes"):
        st.caption(f"ℹ️ Istoricul de preț de la Yahoo a fost corectat pentru calculele de mai jos: {data['price_clean_notes']}.")
    price = data["current_price"]
    checklist_price = price
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Preț curent (Yahoo)", f"{price:.2f} {data.get('currency', '')}")

    if data["week52_high"] is not None and data["week52_low"] is not None:
        pct_from_high = (price / data["week52_high"] - 1) * 100
        checklist_drawdown_52w = pct_from_high
        pct_from_low = (price / data["week52_low"] - 1) * 100
        t2.metric("Față de max. 52 săpt.", f"{pct_from_high:+.1f}%", f"max: {data['week52_high']:.2f}",
                  help="Cât e prețul curent față de maximul din ultimele 52 săptămâni.")
        t3.metric("Față de min. 52 săpt.", f"{pct_from_low:+.1f}%", f"min: {data['week52_low']:.2f}",
                  help="Cât e prețul curent față de minimul din ultimele 52 săptămâni.")
    else:
        t2.metric("Față de max. 52 săpt.", "n/a")
        t3.metric("Față de min. 52 săpt.", "n/a")

    rsi = data["rsi14"]
    if rsi is not None and not np.isnan(rsi):
        rsi_label = "supracumpărat" if rsi > 70 else ("supravândut" if rsi < 30 else "neutru")
        t4.metric("RSI (14)", f"{rsi:.1f}", rsi_label,
                  help="Reper clasic: peste 70 = supracumpărat, sub 30 = supravândut, 30-70 = neutru.")
    else:
        t4.metric("RSI (14)", "n/a")

    yccy = data.get("currency", "")
    s1, s2, s3, s4 = st.columns(4)
    sma20, sma50, sma200 = data["sma20"], data["sma50"], data["sma200"]
    checklist_sma200 = sma200
    s1.metric("SMA 20 zile", f"{sma20:.2f} {yccy}" if sma20 is not None else "n/a", help="Media mobilă pe termen foarte scurt.")
    if sma50 is not None:
        s2.metric("SMA 50 zile", f"{sma50:.2f} {yccy}", "peste ↑" if price > sma50 else "sub ↓",
                  help="Media mobilă pe termen mediu. Preț peste SMA50 e semn orientativ de trend ascendent.")
    else:
        s2.metric("SMA 50 zile", "n/a")
    if sma200 is not None:
        s3.metric("SMA 200 zile", f"{sma200:.2f} {yccy}", "peste ↑" if price > sma200 else "sub ↓",
                  help="Media mobilă pe termen lung. SMA50 peste SMA200 ('golden cross') e considerat bullish.")
    else:
        s3.metric("SMA 200 zile", "n/a")
    s4.metric("Beta", f"{data['beta']:.2f}" if data['beta'] is not None else "n/a",
              help="Cât de mult se mișcă titlul relativ la piață. Beta 1 = mișcare similară pieței; peste 1 = mai volatil; sub 1 = mai stabil.")

    s5, s6 = st.columns(2)
    s5.metric("Volatilitate anualizată", f"{data['volatility_annual_pct']:.1f}%" if data['volatility_annual_pct'] is not None else "n/a",
              help="Fluctuația prețului în ultimul an, anualizată. Sub ~15% scăzută, 15-30% medie, peste 30-40% ridicată.")
    s6.metric("ATR (14 zile)", f"{data['atr14']:.2f} {yccy}" if data['atr14'] is not None else "n/a",
              help="Average True Range — mișcarea medie zilnică a prețului în valoare absolută. Util pentru a seta "
                   "stop-loss realiste, proporționale cu cât 'respiră' normal titlul.")

    st.subheader("📅 Performanță istorică")
    checklist_ret_3m = data.get("perf_quarter_pct")
    perf_cols = st.columns(4)
    for col, label, key in [
        (perf_cols[0], "1 săptămână", "perf_week_pct"), (perf_cols[1], "1 lună", "perf_month_pct"),
        (perf_cols[2], "1 trimestru", "perf_quarter_pct"), (perf_cols[3], "6 luni", "perf_half_year_pct"),
    ]:
        val = data.get(key)
        col.metric(label, f"{val:+.1f}%" if val is not None else "n/a")
    p1, p2, p3, p4, p5 = st.columns(5)
    for col, label, key in [
        (p1, "YTD", "perf_ytd_pct"), (p2, "1 an", "perf_year_pct"), (p3, "3 ani", "perf_3y_pct"),
        (p4, "5 ani", "perf_5y_pct"), (p5, "10 ani", "perf_10y_pct"),
    ]:
        val = data.get(key)
        col.metric(label, f"{val:+.1f}%" if val is not None else "n/a")

    if sma50 and sma200:
        if price > sma50 > sma200:
            st.success("Trend tehnic: bullish — preț peste SMA50, care e peste SMA200.")
        elif price < sma50 < sma200:
            st.error("Trend tehnic: bearish — preț sub SMA50, care e sub SMA200.")
        else:
            st.info("Trend tehnic: mixt — semnalele SMA50/SMA200 nu sunt aliniate.")

    st.markdown("---")

    # --- target analiști ---
    if data.get("target_mean_price") or data.get("number_of_analysts"):
        render_analyst_section(yahoo_symbol, price, yccy, ticker)
        st.markdown("---")

    # --- semnale (informativ) ---
    st.subheader("🧭 Semnale (informativ — nu e sfat de investiții)")
    pro, contra, neutru = [], [], []

    if data['trailing_pe'] is not None:
        if data['trailing_pe'] < 15:
            pro.append(f"P/E ({data['trailing_pe']:.1f}) sub 15 — reper generic de valuation scăzută.")
        elif data['trailing_pe'] > 30:
            contra.append(f"P/E ({data['trailing_pe']:.1f}) peste 30 — reper generic de valuation ridicată.")
    if data['peg_ratio'] is not None:
        if data['peg_ratio'] < 1:
            pro.append(f"PEG ({data['peg_ratio']:.2f}) sub 1 — creșterea ar putea justifica valuation-ul.")
        elif data['peg_ratio'] > 2:
            contra.append(f"PEG ({data['peg_ratio']:.2f}) peste 2 — scump relativ la creșterea estimată.")
    if rsi is not None and not np.isnan(rsi):
        if rsi > 70:
            contra.append(f"RSI ({rsi:.0f}) în zonă de supracumpărare.")
        elif rsi < 30:
            pro.append(f"RSI ({rsi:.0f}) în zonă de supravânzare — posibil rebound tehnic.")
    if sma50 is not None and sma200 is not None:
        if price > sma50 > sma200:
            pro.append("Trend tehnic bullish (preț > SMA50 > SMA200).")
        elif price < sma50 < sma200:
            contra.append("Trend tehnic bearish (preț < SMA50 < SMA200).")
    if data["week52_high"] is not None and price / data["week52_high"] > 0.97:
        neutru.append("Aproape de maximul din ultimele 52 săptămâni — verifică dacă mai are teren de creștere sau e supraextins.")
    if data["week52_low"] is not None and price / data["week52_low"] < 1.05:
        neutru.append("Aproape de minimul din ultimele 52 săptămâni — verifică dacă e oportunitate sau problemă fundamentală.")
    if data['dividend_yield_pct'] is not None and data['dividend_yield_pct'] > 4:
        pro.append(f"Dividend yield generos ({data['dividend_yield_pct']:.1f}%) — verifică sustenabilitatea lui.")
    if data['profit_margin_pct'] is not None and data['profit_margin_pct'] < 0:
        contra.append("Marjă de profit netă negativă (compania e pe pierdere).")
    if data['roe_pct'] is not None and data['roe_pct'] > 15:
        pro.append(f"ROE ({data['roe_pct']:.1f}%) peste 15% — reper generic de eficiență solidă a capitalului propriu.")

    sc1, sc2 = st.columns(2)
    with sc1:
        st.markdown("**✅ Argumente pro**")
        if pro:
            for p in pro:
                st.markdown(f"- {p}")
        else:
            st.caption("Niciun semnal pozitiv clar din regulile curente.")
    with sc2:
        st.markdown("**⚠️ Argumente contra**")
        if contra:
            for c in contra:
                st.markdown(f"- {c}")
        else:
            st.caption("Niciun semnal negativ clar din regulile curente.")
    if neutru:
        st.markdown("**ℹ️ De verificat**")
        for n in neutru:
            st.markdown(f"- {n}")

    st.caption(
        "Lista e generată automat din reguli simple, generice, pe baza indicatorilor calculați mai sus — "
        "nu e sfat de investiții, doar un rezumat al semnalelor tehnice/fundamentale disponibile. Decizia rămâne a ta."
    )

    st.markdown("---")

    with checklist_box:
        st.subheader("✅ Înainte de cumpărare")
        _targets = target_portfolios(ticker, position_row, yahoo_symbol, total_portfolio_value, account_currency, is_watch)
        _labels = [t["label"] for t in _targets]
        _held = [t for t in _targets if t["holds"]]
        _default = max(_held, key=lambda t: t["value_ref"])["label"] if _held else "Trading 212"
        _tlabel = st.selectbox(
            "Portofoliu țintă",
            _labels,
            index=_labels.index(_default) if _default in _labels else 0,
            key=f"chk_target_{ticker}",
            help="Portofoliul în care ai cumpăra. Ponderea după cumpărare se calculează față de valoarea pozițiilor din acel portofoliu (fără cash).",
        )
        _t = next(t for t in _targets if t["label"] == _tlabel)
        amount = st.number_input(
            f"Sumă ipotetică de cumpărat (în {_t['currency']})",
            min_value=0.0,
            value=0.0,
            step=100.0,
            key=f"chk_amt_{ticker}_{_tlabel}",
        )
        current = _t["current_value"]
        total = _t["total_value"]
        if (total + amount) > 0 and (current > 0 or amount > 0):
            weight_after = (current + amount) / (total + amount) * 100
        else:
            weight_after = None

        checklist = build_checklist(
            quality_total=checklist_quality_total,
            quality_coverage=checklist_quality_coverage,
            quality_rating=checklist_quality_rating,
            risk_total=checklist_risk_total,
            risk_coverage=checklist_risk_coverage,
            valuation_red=checklist_valuation_red,
            valuation_usable=checklist_valuation_usable,
            drawdown_52w=checklist_drawdown_52w,
            price=checklist_price,
            sma200=checklist_sma200,
            ret_3m=checklist_ret_3m,
            weight_after=weight_after,
            is_etf=is_etf,
        )
        emoji_by_status = {"green": "🟢", "yellow": "🟡", "red": "🔴", "grey": "⚪"}

        for row in checklist["rows"]:
            st.markdown(
                f"{emoji_by_status.get(row['status'], '⚪')} **{row['label']}**: {row['detail']}",
                help=checklist_tooltip(row["key"]),
            )

        red_rows = checklist["counts"].get("red", 0)
        yellow_rows = checklist["counts"].get("yellow", 0)
        st.caption(
            "Semafoarele sunt reguli generale, nu un verdict; verde peste tot nu înseamnă „cumpără”. "
            f"Rânduri roșii: {red_rows}; galbene: {yellow_rows}."
        )

    # --- notițe personale ---
    st.subheader("📝 Notițele tale")
    notes = load_notes()
    note_text = st.text_area(
        "Notează aici orice vrei să ții minte despre poziția asta (teză de investiție, motive de hold, praguri de vânzare etc.)",
        value=notes.get(ticker, ""), height=150, key=f"note_area_{ticker}",
    )
    if st.button("💾 Salvează notița", key=f"save_note_{ticker}"):
        save_note(ticker, note_text)
        st.success("Notiță salvată.")

    _render_orders()


# --- profilare opțională: `touch profile_on` în folderul proiectului ---
import os as _os, sys as _sys, cProfile as _cp, pstats as _ps, io as _io
_PROFILE_FLAG = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "profile_on")
_render_detail_view_orig = render_detail_view


def render_detail_view(*a, **k):
    if not _os.path.exists(_PROFILE_FLAG):
        return _render_detail_view_orig(*a, **k)
    pr = _cp.Profile()
    pr.enable()
    try:
        return _render_detail_view_orig(*a, **k)
    finally:
        pr.disable()
        buf = _io.StringIO()
        _ps.Stats(pr, stream=buf).sort_stats("cumulative").print_stats(35)
        print("=== PROFIL detail ===\n" + buf.getvalue(), file=_sys.stderr, flush=True)
