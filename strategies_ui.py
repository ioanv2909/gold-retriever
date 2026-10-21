"""Lentilele de strategie: sectiunea din pagina pozitiei si tab-ul Strategii (matricea pozitii x lentile)."""
import pandas as pd
import streamlit as st

import strategies
from i18n import t
from yf_compat import yf, YFINANCE_AVAILABLE

DOTS = {"strong": "🟢", "mixed": "🟡", "weak": "🔴", "trap": "🔴", "insufficient": "⚪", "na": "⚪"}
FMT = {
    "pe_vs_hist": "{:.2f}x", "fcf_yield": "{:.1f}%", "ey_spread": "{:+.1f} pp", "graham_upside": "{:+.0f}%",
    "piotroski": "{:.1f}/9", "ev_ebitda": "{:.1f}x",
    "rev_cagr": "{:+.1f}%", "eps_cagr": "{:+.1f}%", "rev_growth_fwd": "{:+.1f}%", "eps_growth_fwd": "{:+.1f}%",
    "eps_rev_90d": "{:+.1f}%", "peg": "{:.2f}", "rule_of_40": "{:.0f}",
    "growth_streak": "{:.0f}", "dgr_3y": "{:+.1f}%", "dgr_5y": "{:+.1f}%", "dgr_10y": "{:+.1f}%", "chowder": "{:.1f}",
    "payout_trend": "{:+.1f} pp", "ddm_margin": "{:+.0f}%",
    "rating_net_90d": "{:+.0f}", "target_net_90d": "{:+.0f}%", "rec_mean": "{:.2f}", "short_float": "{:.1f}%",
    "short_change": "{:+.0f}%", "insider_net": "{:+.3f}%", "inst_change": "{:+.1f}%", "news_tone": "{:+.0f}",
    "mom_12_1": "{:+.1f}%", "rel_6m": "{:+.1f} pp", "sma200_z": "{:+.2f}σ", "rsi14": "{:.0f}",
    "beat_rate": "{:.0f}%", "avg_surprise": "{:+.1f}%", "avg_reaction": "{:+.1f}%", "event_balance": "{:+.0f}",
}
TONES = {1: "🟢", 0: "⚪", -1: "🔴"}
FILTERS = ("all", "positive", "negative")
# o singura nuanta (verde), mai inchisa cu scorul; treptele urmeaza pragurile 50 / 65 ale lentilelor
SHADES = ((35, "#eef7f1", "#1a1a1a"), (50, "#d3eddc", "#1a1a1a"), (65, "#a6dbb9", "#10301f"),
          (80, "#5fb889", "#0b2416"), (101, "#1f7a4d", "#ffffff"))


def _shade(v):
    if v is None or v != v:
        return ""
    for upper, bg, fg in SHADES:
        if v < upper:
            return "background-color: %s; color: %s" % (bg, fg)
    return ""


def _fmt(key, v):
    if isinstance(v, str):
        return v
    return FMT.get(key, "{:.2f}").format(v) if v is not None else "n/a"


@st.cache_data(ttl=21600, show_spinner=False)
def _rf():
    return strategies.fetch_rf()


@st.cache_data(ttl=21600, show_spinner=False)
def get_metrics(yahoo_symbol):
    import signals
    if not YFINANCE_AVAILABLE:
        return None
    try:
        return strategies.extract_metrics(yf.Ticker(yahoo_symbol), _rf(), symbol=yahoo_symbol,
                                          ua_email=signals.ua_email())
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _live_market():
    import signals
    return signals.market_context()


def _market(cache):
    mk = cache.get(strategies.MARKET_KEY) or {}
    return mk if mk.get("vix") is not None or mk.get("spx_vs_sma200") is not None else _live_market()


def _market_text(mk):
    """Contextul pietei intr-o linie: VIX si S&P 500 fata de SMA200."""
    parts = []
    vix = mk.get("vix")
    if vix is not None:
        mood = "calm" if vix < 15 else "normal" if vix < 25 else "tense"
        parts.append(t("st.market_vix", v="%.1f" % vix, mood=t("st.market_mood." + mood)))
    spx = mk.get("spx_vs_sma200")
    if spx is not None:
        parts.append(t("st.market_spx_" + ("above" if spx >= 0 else "below"), p="%+.1f" % spx))
    return t("st.market", parts=" · ".join(parts)) if parts else None


def _quality(ticker, qcache=None):
    """Scorul de calitate din cache (pentru capcana de valoare), doar cu acoperire suficienta."""
    if qcache is None:
        from background import load_quality_cache
        qcache = load_quality_cache()
    q = qcache.get(ticker) or {}
    return q.get("total") if (q.get("coverage") or 0) >= 50 else None


def _verdict(r):
    if r["level"] == "na":
        return t("st.na." + r.get("reason", "no_data"))
    if r["level"] == "insufficient":
        return t("st.v.insufficient")
    return t("st.v.%s.%s" % (r["lens"], r["level"]))


def _conv_text(pos, neg, known):
    if not known:
        return t("st.conv_none")
    return t("st.conv", pos=pos, neg=neg, n=known)


def _profile_label(name, lenses):
    if name == strategies.CUSTOM:
        return t("st.profile.custom") + " (" + ", ".join(t("st.lens." + x) for x in lenses) + ")"
    return t("st.profile." + name)


def _profile_picker():
    """Profilul de investitor al utilizatorului: alege lentilele care conteaza la convergenta."""
    name, lenses = strategies.load_profile()
    names = list(strategies.PROFILES) + [strategies.CUSTOM]
    c1, c2 = st.columns([2, 5], vertical_alignment="bottom")
    new = c1.selectbox(t("st.profile"), names, index=names.index(name), key="st_profile",
                       format_func=lambda k: t("st.profile." + k), help=t("st.profile_help"))
    if new == strategies.CUSTOM:
        chosen = c2.multiselect(t("st.profile_lenses"), list(strategies.LENSES), default=list(lenses),
                                format_func=lambda k: t("st.lens." + k), key="st_profile_lenses")
        if chosen and (new != name or tuple(chosen) != tuple(lenses)):
            name, lenses = strategies.save_profile(new, chosen)
    else:
        c2.caption(t("st.profile_uses", lenses=", ".join(t("st.lens." + x) for x in strategies.PROFILES[new])))
        if new != name:
            name, lenses = strategies.save_profile(new)
    return name, lenses


def _rows_table(r):
    return pd.DataFrame([{
        t("st.col.indicator"): t("st.ind." + row["key"]),
        t("st.col.value"): _fmt(row["key"], row["value"]),
        t("st.col.target"): _fmt(row["key"], row["target"]),
        t("st.col.red_flag"): _fmt(row["key"], row["red_flag"]),
        t("st.col.score"): f"{row['score'] * 100:.0f}/100" if row["score"] is not None else "n/a",
        t("st.col.why"): t("st.why." + row["key"]),
    } for row in r["rows"]])


def _ddm_details(x):
    st.caption(t("st.ddm_assume", d0="%.2f" % x["d0"], rf="%.1f" % x["rf"], beta="%.2f" % x["beta"],
                 erp="%.1f" % x["erp"], r="%.1f" % x["r"], g1="%.1f" % x["g1"], g2="%.1f" % x["g2"], n=strategies.STAGE1_YEARS,
                 gh="%.1f%%" % x["g_hist"] if x["g_hist"] is not None else "n/a",
                 gs="%.1f%%" % x["g_sust"] if x["g_sust"] is not None else "n/a"))
    st.markdown(t("st.ddm_result", v="%.2f" % x["value"], p="%.2f" % x["price"], m="%+.0f" % x["margin"]))
    cols = {dg: t("st.ddm_g", g="%.1f" % max(x["g1"] + dg, 0)) for dg in (-1, 0, 1)}
    table = []
    for dr in (-1, 0, 1):
        row = {t("st.ddm_r_col"): "r = %.1f%%" % (x["r"] + dr)}
        for dg in (-1, 0, 1):
            v = x["sens"].get("%d,%d" % (dr, dg))
            row[cols[dg]] = "%.2f (%+.0f%%)" % (v, (v / x["price"] - 1) * 100) if v else "n/a"
        table.append(row)
    st.markdown("**" + t("st.ddm_sens") + "**")
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    st.caption(t("st.ddm_sens_note"))


def _next_earnings(ticker):
    import events
    up = [e for e in events.upcoming(events.load_cache(), [ticker], days=90) if e["type"] == "earnings"]
    return up[0] if up else None


def _events_details(ticker, x):
    nxt = _next_earnings(ticker)
    if nxt:
        st.markdown(t("st.next_earnings", d=nxt["date"], n=nxt["days"]))
    evs = x.get("events") or []
    if evs:
        st.markdown("**" + t("st.timeline") + "**")
        st.dataframe(pd.DataFrame([{
            t("st.tl.date"): e["date"],
            t("st.tl.source"): t("st.src." + e["source"]),
            t("st.tl.kind"): t("st.kind." + e["kind"]) if e.get("kind") else "",
            t("st.tl.tone"): TONES.get(e["tone"], "⚪"),
            t("st.tl.title"): e["title"],
            t("st.tl.link"): e.get("link"),
        } for e in evs]), hide_index=True, width="stretch",
            column_config={t("st.tl.link"): st.column_config.LinkColumn(t("st.tl.link"), display_text="↗")})
    else:
        st.caption(t("st.timeline_empty"))
    st.caption(t("st.sec_on") if x.get("sec_checked") else t("st.sec_off"))


def render_strategy_section(ticker, yahoo_symbol, position_row):
    """Sectiunea Strategii din pagina unei actiuni: un card pe lentila, apoi detaliile fiecareia."""
    st.subheader(t("st.title"))
    entry = strategies.load_cache().get(ticker) or {}
    m = entry.get("m") if entry.get("symbol") == yahoo_symbol else None
    if not m:
        with st.spinner(t("st.loading_one")):
            m = get_metrics(yahoo_symbol)
    mk = _market(strategies.load_cache())
    results = strategies.evaluate(m, _quality(ticker), market=mk)
    pname, plenses = strategies.load_profile()
    pos, neg, known = strategies.convergence(results, plenses)
    st.caption(t("st.conv_profile", p=_profile_label(pname, plenses)) + " " + _conv_text(pos, neg, known))

    market = _market_text(mk)
    if market:
        st.caption(market)

    etf = (m or {}).get("kind") == "etf"
    # lentilele profilului primele; la ETF-uri doar cele care se aplica (Trend)
    lenses = [x for x in plenses] + [x for x in strategies.LENSES if x not in plenses]
    if etf:
        lenses = [x for x in lenses if results[x]["applicable"]]
    cols = [c for _ in range(0, len(lenses), 3) for c in st.columns(3)]
    for c, lens in zip(cols, lenses):
        r = results[lens]
        with c.container(border=True):
            mark = " ★" if lens in plenses and len(plenses) < len(strategies.LENSES) else ""
            st.markdown("**%s%s**" % (t("st.lens." + lens), mark))
            score = "%.0f/100" % r["total"] if r["total"] is not None and r["level"] != "insufficient" else "n/a"
            st.markdown("### %s %s" % (DOTS[r["level"]], score))
            st.caption(_verdict(r))

    for lens in lenses:
        r = results[lens]
        if not r["applicable"]:
            continue
        with st.expander(t("st.details", lens=t("st.lens." + lens))):
            if lens == "ddm":
                _ddm_details(r["extra"])
            st.dataframe(_rows_table(r), hide_index=True, width="stretch")
            if lens == "value":
                x = r["extra"]
                if x.get("piotroski_n"):
                    st.caption(t("st.piotroski_note", p=x["piotroski_raw"], n=x["piotroski_n"]))
                if x.get("pe") and x.get("pe_hist"):
                    st.caption(t("st.pe_note", pe="%.1f" % x["pe"], h="%.1f" % x["pe_hist"]))
            if lens == "sentiment":
                x = r["extra"]
                st.caption(t("st.sent_counts", up=x.get("upgrades") or 0, down=x.get("downgrades") or 0,
                             r=x.get("raises") or 0, l=x.get("lowers") or 0, b=x.get("insider_buys") or 0,
                             s=x.get("insider_sells") or 0, n=x.get("news_n") or 0))
            if lens == "events":
                _events_details(ticker, r["extra"])
            if lens == "trend":
                x = r["extra"]
                if x.get("ret_6m") is not None and x.get("spx_ret_6m") is not None:
                    st.caption(t("st.trend_6m", r="%+.1f" % x["ret_6m"], s="%+.1f" % x["spx_ret_6m"]))
                if x.get("sma200_dist") is not None:
                    st.caption(t("st.trend_sma", d="%+.1f" % x["sma200_dist"]))
                if x.get("overextended"):
                    st.warning(t("st.overextended"))
            if lens == "div_growth":
                x = r["extra"]
                avg, cur = position_row.get("averagePrice"), position_row.get("currentPrice")
                if x.get("div_yield") and avg and cur and not position_row.get("watchlist"):
                    st.caption(t("st.yoc", y="%.2f" % x["div_yield"], yoc="%.2f" % (x["div_yield"] * cur / avg)))
            st.caption(t("st.coverage", c="%.0f" % r["coverage"]))
    st.caption(t("st.disclaimer"))


def _matrix(vdf, cache, plenses=strategies.LENSES):
    from background import load_quality_cache
    qcache = load_quality_cache()
    mk = _market(cache)
    rows = []
    seen = set()
    for rec in vdf.to_dict("records"):
        tk = rec.get("ticker")
        if not tk or tk in seen:
            continue
        seen.add(tk)
        entry = cache.get(tk) or {}
        res = strategies.evaluate(entry.get("m"), _quality(tk, qcache), market=mk)
        pos, neg, known = strategies.convergence(res, plenses)

        def score(lens):
            r = res[lens]
            return r["total"] if r["level"] not in ("na", "insufficient") else None

        ddm = res["ddm"]
        rows.append({
            "ticker": tk, "name": rec.get("name") or "",
            "value": score("value"), "growth": score("growth"), "ddm": score("ddm"), "div_growth": score("div_growth"),
            "sentiment": score("sentiment"), "events": score("events"), "trend": score("trend"),
            "ddm_margin": ddm["extra"].get("margin") if ddm["applicable"] else None,
            "conv": _conv_text(pos, neg, known) if entry else t("st.na.no_data"),
            "note": " · ".join(x for x in (t("st.trap") if res["value"]["level"] == "trap" else "",
                                           t("st.overext_short") if res["trend"]["extra"].get("overextended") else "")
                               if x),
            "_pos": pos, "_neg": neg, "_known": known,
        })
    return sorted(rows, key=lambda r: (-(r["_pos"] - r["_neg"]), -r["_pos"], r["ticker"]))


def render_strategies_tab(vdf):
    """vdf: randurile pozitiilor din portofoliile selectate (ticker, name)."""
    if vdf is None or vdf.empty:
        st.info(t("ex.empty"))
        return
    status = strategies.load_status()
    cache = strategies.load_cache()
    tickers = list(dict.fromkeys(vdf["ticker"].dropna()))

    c1, c2 = st.columns([6, 2], vertical_alignment="bottom")
    flt = c1.segmented_control(t("st.filter"), FILTERS, default="all", format_func=lambda k: t("st.filter." + k),
                               key="st_filter")
    if c2.button(t("st.refresh"), key="st_refresh", disabled=bool(status.get("in_progress"))):
        missing = [tk for tk in tickers if tk not in cache]
        strategies.start_fetch_background(missing or tickers)
        st.rerun()
    if status.get("in_progress"):
        st.caption(t("st.loading", done=status.get("done", 0), total=status.get("total", 0)))

    market = _market_text(_market(cache))
    if market:
        st.caption(market)

    pname, plenses = _profile_picker()
    rows = _matrix(vdf, cache, plenses)
    if flt == "positive":
        rows = [r for r in rows if r["_pos"] >= 2 and r["_pos"] > r["_neg"]]
    elif flt == "negative":
        rows = [r for r in rows if r["_neg"] >= 2 and r["_neg"] > r["_pos"]]
    if not rows:
        st.info(t("st.empty"))
        return

    df = pd.DataFrame(rows).drop(columns=["_pos", "_neg", "_known"])
    score_col = lambda lens: st.column_config.Column(t("st.lens." + lens), help=t("st.lens_help." + lens))
    # lentilele din afara profilului raman vizibile, dar estompate (nu intra in convergenta)
    inside = [x for x in strategies.LENSES if x in plenses]
    outside = [x for x in strategies.LENSES if x not in plenses]
    styled = df.style.format({lens: "{:.0f}/100" for lens in strategies.LENSES} | {"ddm_margin": "{:+.0f}%"},
                             na_rep="—").map(_shade, subset=inside)
    if outside:
        styled = styled.map(lambda v: "color: #8a8a8a", subset=outside)
    event = st.dataframe(
        styled, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        key="st_table_%d" % st.session_state.get("table_nonce", 0),
        column_config={
            "ticker": st.column_config.TextColumn(t("st.col.ticker"), help=t("st.col.ticker_help")),
            "name": st.column_config.TextColumn(t("st.col.name"), help=t("st.col.name_help")),
            "value": score_col("value"), "growth": score_col("growth"), "ddm": score_col("ddm"),
            "div_growth": score_col("div_growth"), "sentiment": score_col("sentiment"), "events": score_col("events"),
            "trend": score_col("trend"),
            "ddm_margin": st.column_config.Column(t("st.col.ddm_margin"), help=t("st.col.ddm_margin_help")),
            "conv": st.column_config.TextColumn(t("st.col.conv"), help=t("st.col.conv_help")),
            "note": st.column_config.TextColumn(t("st.col.note"), help=t("st.col.note_help")),
        })
    sel = event.selection.rows if event and event.selection else []
    if sel:
        tk = rows[sel[0]]["ticker"]
        detail = {r["ticker"]: r for r in st.session_state.get("_table_rows", [])}.get(tk)
        if detail:
            st.session_state["selected_ticker"] = tk
            st.session_state["selected_row"] = detail
            st.session_state["total_portfolio_value"] = st.session_state.get("_table_total")
            st.session_state["scroll_to_top_detail"] = True
            st.rerun()
    st.caption(t("st.scale"))
    if outside:
        st.caption(t("st.outside_note"))
    st.caption(t("st.tab_note"))
    st.caption(t("st.disclaimer"))
