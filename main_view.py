"""Pagina principala: antet, sumar, istoric, pozitii si taburile secundare."""
import base64
import os
from datetime import datetime

import streamlit as st

import mobile
import privacy
from auth import auto_rerun, user_menu
from background import load_dividends_status, load_market_context_cache, load_quality_cache, load_ratings_status
from cash_ui import render_cash
from core import RECOMMENDATION_LABELS, check_loss_to_profit_alerts, dismiss_alert, record_portfolio_point
from detail_view import scroll_page_to_top
from history_ui import render_history
from i18n import lang_button, t, x as _tx
from navigation import open_detail_from_url
from lang_prefs import load_pref, save_pref
from portfolio_model import build_rows, portfolio_options
from position_alerts_ui import render_banner as _alerts_banner
from positions_data import build_t212_frame, enrich_view, finish_t212_frame
from positions_table_ui import render_positions_table
from privacy import mask as _mask
from t212_api import fetch_account_currency, load_cached_dividends, load_cached_ratings, load_cached_snapshot
from url_tabs import url_tabs
from watchlist_ui import render_watchlist_tab
from xtb import accounts_summary

DEFAULT_DISPLAY_CCY = "EUR"
_CCY_OPTIONS = ["EUR", "USD", "GBP", "CHF", "RON", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK",
                "ISK", "BGN", "TRY", "UAH", "RSD", "CAD", "AUD", "NZD", "JPY", "CNY", "HKD", "SGD",
                "KRW", "INR", "ILS", "ZAR", "BRL", "MXN"]


@st.fragment(run_every=5)
def _watch_background_jobs():
    busy = load_dividends_status().get("in_progress") or load_ratings_status().get("in_progress")
    if not busy:
        auto_rerun()


def _render_header(me, compact, detail_loading):
    """Banner demo, sigla, titlu, limba, meniul utilizatorului, alertele si titlul sumarului."""
    try:
        import userctx as _uc
        _uname = _uc.current_user() or ""
    except Exception:
        _uname = ""
    if _uname == "demo":
        _ro = str(st.session_state.get("lang", "")).upper().startswith("RO")
        st.info(
            "Cont demo: toate datele sunt fictive (tickere și prețuri reale, achiziții inventate). Nu reprezintă sfaturi financiare."
            if _ro else
            "Demo account: all data is fictional (real tickers and prices, invented purchases). This is not financial advice.",
            icon="🧪",
        )
    import appearance
    appearance.sticky_header("app_header")  # stilul si culorile temei inainte de bara, ca sa nu adauge spatiu in ea
    _hdr = st.container(key="app_header")
    # pe telefon fara sigla si titlu (sigla apare la login), doar limba si utilizatorul
    if compact:
        _c_lang, _c_user = _hdr.columns([1, 3], vertical_alignment="center")
    else:
        _c_logo, _c_title, _c_lang, _c_user = _hdr.columns([1, 14, 2, 3], vertical_alignment="center")
        with _c_logo:
            if os.path.exists("assets/icon-192.png"):
                with open("assets/icon-192.png", "rb") as _f:
                    st.markdown(
                        '<img class="gr-logo" src="data:image/png;base64,%s" width="64">' % base64.b64encode(_f.read()).decode(),
                        unsafe_allow_html=True,
                    )
        with _c_title:
            st.title(t("app.title"))
    with _c_lang:
        lang_button("lang_switch")
    with _c_user:
        user_menu(me)

    _alerts_banner()

    snapshot = load_cached_snapshot()
    if snapshot and snapshot.get("positions"):
        instruments_by_ticker = {}
        if snapshot.get("instruments"):
            instruments_by_ticker = {i.get("ticker"): i.get("name", i.get("ticker")) for i in snapshot["instruments"]}
        active_alerts = [a for a in check_loss_to_profit_alerts(snapshot["positions"], instruments_by_ticker) if not a.get("dismissed")]
        for a in active_alerts:
            from position_alerts_ui import banner_row
            _txt = t("alert.loss_to_profit", name=a["name"], ticker=a["ticker"], days=a["zile_detinut"], pct=f"{a['randament_%']:.2f}")
            if banner_row("profit", _txt.removeprefix("⚠️ "), t("alert.seen"),
                          f"dismiss_{a['ticker']}_{a['triggered_at']}", icon="📈 ",
                          ts=a.get("triggered_at"), detail=(a["ticker"], a["name"])):
                dismiss_alert(a["ticker"], a["triggered_at"])
                st.rerun()

    if not detail_loading:
        _sum_t, _sum_eye = st.columns([5, 2], vertical_alignment="bottom")
        _sum_t.subheader(t("app.summary"))
        with _sum_eye:
            privacy.toggle_button("privacy_toggle")


def _pick_portfolios(has_t212, account_currency, detail_loading):
    """Portofoliile si moneda afisata (alese pe pagina, pastrate in _ui_prefs pentru pagina de detaliu)."""
    _ui = st.session_state.setdefault("_ui_prefs", {})
    _opts = [o for o in portfolio_options() if has_t212 or o != "Trading 212"]
    _ccy_opts = list(_CCY_OPTIONS)
    for _c in [account_currency] + [a["currency"] for a in accounts_summary()]:
        if _c and _c != "?" and _c not in _ccy_opts:
            _ccy_opts.insert(0, _c)
    if detail_loading:
        sel_portfolios = [x for x in _ui.get("portfolios", _opts) if x in _opts] or list(_opts)
        display_ccy = _ui.get("ccy") or load_pref("display_ccy") or DEFAULT_DISPLAY_CCY
        _ui.setdefault("ccy", display_ccy)
        return sel_portfolios, display_ccy
    _cur = [x for x in st.session_state.get("portfolio_sel", _ui.get("portfolios", _opts)) if x in _opts]
    st.session_state["portfolio_sel"] = _cur or list(_opts)
    _col_p, _col_c = st.columns([3, 2])
    with _col_p:
        if len(_opts) > 1:
            _picked = st.pills(t("main.portfolios"), _opts, selection_mode="multi", key="portfolio_sel")
        else:
            _picked = list(_opts)
    sel_portfolios = list(_picked or []) or list(_opts)
    # moneda aleasa ramane la reincarcarea paginii si la schimbarea portofoliilor (salvata per utilizator);
    # fara alegere salvata: EUR
    _saved_ccy = load_pref("display_ccy")
    _dflt_ccy = _saved_ccy if _saved_ccy in _ccy_opts else DEFAULT_DISPLAY_CCY
    if st.session_state.get("display_ccy") not in _ccy_opts:
        st.session_state["display_ccy"] = _ui.get("ccy") if _ui.get("ccy") in _ccy_opts else _dflt_ccy
    with _col_c:
        st.markdown("<style>.st-key-display_ccy{max-width:7rem;}</style>", unsafe_allow_html=True)
        _picked_ccy = st.selectbox(t("main.display_ccy"), _ccy_opts, key="display_ccy")
    display_ccy = _picked_ccy or _dflt_ccy
    save_pref("display_ccy", display_ccy)
    _ui["portfolios"] = sel_portfolios
    _ui["ccy"] = display_ccy
    return sel_portfolios, display_ccy


def _deposit_stats(sel_portfolios, display_ccy):
    """(data de start, depuneri nete, luni, ritm lunar) in display_ccy pentru portofoliile alese;
    operatiunile se citesc din jurnal cel mult o data pe ora."""
    import time
    import journal
    import pace_target
    _c = st.session_state.get("_first_inv_cache")
    if not _c or time.time() - _c[0] > 3600:
        try:
            ops = journal.load_all({})
        except Exception:
            ops = []
        _c = (time.time(), [op for op in ops if op["type"] in ("deposit", "withdrawal", "buy")])
        st.session_state["_first_inv_cache"] = _c
    return pace_target.pace_of(_c[1], display_ccy, set(sel_portfolios))


def _invested_metric(col, label, invested, sel_portfolios, display_ccy):
    """Total investit, cu ritmul lunar (depuneri nete / luni de la prima investitie) ca delta."""
    start, net, months, pace = _deposit_stats(sel_portfolios, display_ccy)
    delta, help_ = None, None
    if pace is not None:
        delta = t("main.monthly_pace", v=_mask(f"{pace:,.2f}"), n=f"{months:.0f}")
        help_ = t("main.monthly_pace_help", d=f"{start:%d.%m.%Y}", v=_mask(f"{net:,.2f} {display_ccy}"))
        # badge-ul colorat dupa tinta lunara din Setari > Obiective (convertita in moneda afisata)
        import pace_target
        from portfolio_model import fx
        _tg = pace_target.load()
        _rate = float(fx(_tg[1], display_ccy) or 0) if _tg else 0.0
        if _rate > 0:
            target = _tg[0] * _rate
            col.markdown(pace_target.badge_css("pace_metric", pace_target.color_for(pace, target)),
                         unsafe_allow_html=True)
            help_ += "\n\n" + t("main.monthly_pace_target", v=_mask(f"{target:,.2f} {display_ccy}"),
                                  p=f"{pace / target * 100:.0f}")
        col = col.container(key="pace_metric")
    col.metric(label, _mask(f"{invested:,.2f}"), delta, delta_color="off", delta_arrow="off", help=help_)


def _peak_caption(col, sel_portfolios, display_ccy, native, current):
    """Sub valoarea de piata: maximul atins de portofoliile alese, cu data, si cat de departe e valoarea de acum."""
    import peaks
    from core import load_portfolio_history
    from history_multi import multi_history_records
    try:
        records = multi_history_records(sel_portfolios, display_ccy)
        if native and len(records) < 2:
            records = load_portfolio_history()
        pk = peaks.portfolio_peak(records, current)
    except Exception:
        pk = None
    if not pk:
        return
    if pk["now"]:
        text = t("peak.portfolio_now")
    else:
        text = t("peak.portfolio", v=_mask(f"{pk['value']:,.2f}"), d=peaks.peak_label(pk["ts"]))
        if current and current > 0:
            text += " · " + t("peak.below", p=f"{(1 - current / pk['value']) * 100:.1f}")
    col.caption(text, help=t("peak.portfolio_help"))


def _render_metrics(native, vdf, cash, total_dividende, display_ccy, sel_portfolios=()):
    col1, col2, col3, col4 = st.container(key="summary_metrics").columns(4)
    # in modul de confidentialitate delta valorii de piata e randamentul %, nu P/L-ul in bani
    if native:
        invested = cash.get("invested", 0.0)
        ppl = cash.get("ppl", 0.0)
        market_value = invested + ppl
        yield_pct = (ppl / invested * 100.0) if invested else 0.0
        _invested_metric(col1, "💰 Total Investit", invested, sel_portfolios, display_ccy)
        col2.metric("📊 Valoare de Piață (Nerealizat)", _mask(f"{market_value:,.2f}"),
                    f"{yield_pct:+.2f}%" if privacy.hidden() else f"{ppl:,.2f}")
        _peak_caption(col2, sel_portfolios, display_ccy, native, market_value)
        col3.metric("📈 Randament", f"{yield_pct:.2f}%")
        col4.metric("💵 Total Dividende Încasate", _mask(f"{total_dividende:,.2f}"))
    else:
        _m_inv = float(vdf["cost_disp"].sum())
        _m_val = float(vdf["value_disp"].sum())
        _m_pl = float(vdf["pl_disp"].sum())
        _m_div = float(vdf["div_disp"].sum())
        _m_yield = (_m_pl / _m_inv * 100.0) if _m_inv else 0.0
        _invested_metric(col1, f"💰 Total Investit ({display_ccy})", _m_inv, sel_portfolios, display_ccy)
        col2.metric(f"📊 Valoare de Piață ({display_ccy})", _mask(f"{_m_val:,.2f}"),
                    f"{_m_yield:+.2f}%" if privacy.hidden() else f"{_m_pl:,.2f}")
        _peak_caption(col2, sel_portfolios, display_ccy, native, _m_val)
        col3.metric("📈 Randament", f"{_m_yield:.2f}%")
        col4.metric(f"💵 Total Dividende Încasate ({display_ccy})", _mask(f"{_m_div:,.2f}"))


def _filter_by_rating(vdf, compact):
    """Filtrul dupa recomandare (doar pe desktop); intoarce randurile ramase."""
    filter_options = ["Toate"] + list(RECOMMENDATION_LABELS.values())
    if compact:
        filter_choice = "Toate"
    else:
        with st.expander(t("side.filters"), expanded=False):
            filter_choice = st.selectbox(t("filter.rating"), filter_options, index=0, key="rec_filter", format_func=_tx)
    if filter_choice != "Toate":
        st.caption(t("filter.active", f=_tx(filter_choice)))
    if "positions_sort_label" not in st.session_state:
        st.session_state["positions_sort_label"] = "Val. curentă"
    if "positions_sort_desc" not in st.session_state:
        st.session_state["positions_sort_desc"] = True
    if filter_choice != "Toate":
        reverse_map = {v: k for k, v in RECOMMENDATION_LABELS.items()}
        target_key = reverse_map.get(filter_choice)
        return vdf[vdf["recomandare"] == target_key].reset_index(drop=True)
    return vdf


def _render_tabs(df, df_display, vdf, display_ccy, total_portfolio_value, compact, detail_loading):
    # pe telefon lipsesc taburile grele (strategii, expunere, comparare)
    _tabs = url_tabs([e for e in [("positions", t("tab.positions")), ("strategies", t("tab.strategies")),
                                  ("exposure", t("tab.exposure")), ("compare", t("tab.compare")),
                                  ("calendar", t("tab.events")), ("journal", t("tab.journal")),
                                  ("markets", t("tab.markets")), ("watchlist", t("tab.watchlist"))]
                      if not (compact and e[0] in ("strategies", "exposure", "compare"))], "main_tab")
    tab_pos, tab_st, tab_ex, tab_cmp, tab_ev, tab_jr, tab_mh, tab_wl = (
        _tabs.get(k) for k in ("positions", "strategies", "exposure", "compare", "calendar", "journal", "markets",
                               "watchlist"))
    with tab_pos:
        render_positions_table(df, df_display, display_ccy, total_portfolio_value, compact)

    # taburile secundare se randeaza doar cand sunt deschise (comparatia descarca preturi)
    if tab_st is not None and tab_st.open is not False:
        with tab_st:
            from strategies_ui import render_strategies_tab
            render_strategies_tab(vdf)

    if tab_ex is not None and tab_ex.open is not False:
        with tab_ex:
            from exposure_ui import render_exposure_tab
            render_exposure_tab(vdf, display_ccy)

    if tab_cmp is not None and tab_cmp.open is not False:
        with tab_cmp:
            from compare_ui import render_compare_tab
            render_compare_tab(vdf)

    if tab_ev.open is not False:
        with tab_ev:
            from events_ui import render_calendar_tab
            render_calendar_tab(dict(zip(df_display["ticker"], df_display["name"])))

    if tab_jr.open is not False:
        with tab_jr:
            from journal_ui import render_journal_tab
            render_journal_tab(dict(zip(df_display["ticker"], df_display["name"])))

    if tab_mh.open is not False:
        with tab_mh:
            from market_hours_ui import render_market_hours_tab
            render_market_hours_tab(vdf)

    if not detail_loading:
        with tab_wl:
            render_watchlist_tab()


def _render_update_notes(div_status, div_snapshot, rat_status, rat_snapshot):
    """Starea actualizarii dividendelor si recomandarilor Trading 212, sub taburi."""
    _notes = []
    if div_status.get("in_progress"):
        _notes.append(t("div.running", done=div_status.get("done", 0), tot=div_status.get("total", 0)))
    elif div_snapshot and div_snapshot.get("fetched_at"):
        _ts_div = datetime.fromtimestamp(div_snapshot["fetched_at"]).strftime("%d.%m.%Y %H:%M:%S")
        _notes.append(t("div.updated", ts=_ts_div) + (f" · ⚠️ {div_snapshot['error']}" if div_snapshot.get("error") else ""))
    else:
        _notes.append(t("div.none"))
    if rat_status.get("in_progress"):
        _notes.append(t("rat.running", done=rat_status.get("done", 0), tot=rat_status.get("total", 0)))
    elif rat_snapshot and rat_snapshot.get("fetched_at"):
        _ts_rat = datetime.fromtimestamp(rat_snapshot["fetched_at"]).strftime("%d.%m.%Y %H:%M:%S")
        _notes.append(t("rat.updated", ts=_ts_rat))
    else:
        _notes.append(t("rat.none"))
    st.caption(" · ".join(_notes))


def render_main_view(me, api_key_id, api_secret):
    detail_loading = bool(st.query_params.get("detail"))
    if st.session_state.pop("scroll_to_top_main", False):
        scroll_page_to_top()
    compact = mobile.compact()
    _render_header(me, compact, detail_loading)

    div_status = load_dividends_status()
    rat_status = load_ratings_status()
    snapshot = load_cached_snapshot()  # re-citit după eventualele butoane de update de mai sus

    if snapshot:
        ts = datetime.fromtimestamp(snapshot["fetched_at"]).strftime("%d.%m.%Y %H:%M:%S")
        st.caption(t("main.updated_at", ts=ts))

    errs = (snapshot or {}).get("errors") or {}
    t212_err = errs.get("cash") or errs.get("portfolio")
    has_t212 = bool(snapshot) and not t212_err
    # cu conturi XTB, lipsa datelor Trading 212 nu mai ascunde restul paginii: T212 continua cu zero pozitii
    has_xtb = bool(accounts_summary())
    if not snapshot and (api_key_id or not has_xtb):
        st.info(t("main.no_cache"))
    elif t212_err:
        st.error(t212_err)
    if not has_t212 and not has_xtb:
        return

    cash = snapshot["cash"] if has_t212 else {}
    if has_t212:
        invested = cash.get("invested", 0.0)
        ppl = cash.get("ppl", 0.0)
        record_portfolio_point(invested + ppl, invested, ppl)

    positions = (snapshot.get("positions") or []) if has_t212 else []
    if not positions and not has_xtb:
        st.info(t("main.no_positions"))
        return

    account_currency, _ = fetch_account_currency(api_key_id, api_secret)
    account_currency = account_currency or "?"
    div_snapshot = load_cached_dividends()
    rat_snapshot = load_cached_ratings()
    ratings = (rat_snapshot or {}).get("ratings", {})
    targets = (rat_snapshot or {}).get("targets", {})
    quality_data = load_quality_cache() or {}
    df, fx_errors, total_portfolio_value, total_dividende = build_t212_frame(
        positions, snapshot.get("instruments") if has_t212 else None, errs.get("instruments"),
        account_currency, (div_snapshot or {}).get("dividends", {}), ratings, quality_data)

    sel_portfolios, display_ccy = _pick_portfolios(has_t212, account_currency, detail_loading)
    native = set(sel_portfolios) == {"Trading 212"} and display_ccy == account_currency
    vdf = build_rows(df, display_ccy, sel_portfolios, account_currency)

    cash_done = False
    if not detail_loading:
        _render_metrics(native, vdf, cash, total_dividende, display_ccy, sel_portfolios)
        cash_done = render_history(
            sel_portfolios, display_ccy, native, compact,
            lambda: render_cash(sel_portfolios, display_ccy, cash, api_key_id, api_secret, compact=True),
            market_rows=vdf)
    if not cash_done:
        render_cash(sel_portfolios, display_ccy, cash, api_key_id, api_secret)

    try:
        from returns_summary import render_returns_summary
        render_returns_summary("Trading 212" in sel_portfolios, any(str(x).startswith("XTB") for x in sel_portfolios))
    except Exception as _e:
        st.caption(t("ret.unavailable", e=_e))

    mc = load_market_context_cache()
    df = finish_t212_frame(df, mc)

    account_currency_note = t("main.fx_error", e="; ".join(fx_errors)) if fx_errors else ""
    if not detail_loading:
        st.subheader(t("main.open_positions"))
    if not compact:
        st.caption(t("main.table_note", ccy=display_ccy) + account_currency_note)
        st.caption(t("main.alpha_note"))
    elif account_currency_note:
        st.caption(account_currency_note)

    open_detail_from_url(df, total_portfolio_value)

    vdf = enrich_view(vdf, ratings, targets, quality_data, mc)
    df_display = _filter_by_rating(vdf, compact)
    if df_display.empty:
        st.info(t("filter.none"))
        return

    if div_snapshot and div_snapshot.get("error"):
        st.caption(t("div.partial_err", e=div_snapshot["error"]))

    _render_tabs(df, df_display, vdf, display_ccy, total_portfolio_value, compact, detail_loading)

    if "Trading 212" in sel_portfolios:
        _render_update_notes(div_status, div_snapshot, rat_status, rat_snapshot)

    if div_status.get("in_progress") or rat_status.get("in_progress"):
        _watch_background_jobs()
