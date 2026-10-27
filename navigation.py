"""Ce pozitie e deschisa: selectia din tabele, ?detail= si ?page= din URL."""
import streamlit as st

import autorefresh
from watchlist_ui import watch_row as _watch_row
from xtb import instruments as _xtb_instruments


def _xtb_detail_row(ticker):
    for i in _xtb_instruments():
        if i.get("ticker") == ticker:
            return {"ticker": ticker, "name": i.get("name") or ticker, "currencyCode": '', "currentPrice": 0.0, "isin": i.get("isin"), "type": "ETF" if i.get("category") in ("ETF", "ETC") else "STOCK", "watchlist": True}
    return None


def open_detail_from_url(df, total_portfolio_value):
    """?detail=<ticker> deschide pozitia (Trading 212, watchlist sau XTB); un ticker necunoscut e scos din URL."""
    detail_ticker = st.query_params.get("detail")
    if detail_ticker and "selected_ticker" not in st.session_state:
        _scroll = not st.session_state.pop(autorefresh.KEEP_SCROLL, False)
        if not _scroll:
            st.session_state["_auto_rerun"] = True  # refacerea randului dupa o reincarcare automata nu e activitate
        match = df[df["ticker"] == detail_ticker]
        if not match.empty:
            st.session_state["selected_ticker"] = match.iloc[0]["ticker"]
            st.session_state["selected_row"] = match.iloc[0].to_dict()
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = _scroll
            st.rerun()
        wrow = _watch_row(detail_ticker)
        if wrow:
            st.session_state["selected_ticker"] = wrow["ticker"]
            st.session_state["selected_row"] = wrow
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = _scroll
            st.rerun()
        xrow = _xtb_detail_row(detail_ticker)
        if xrow:
            st.session_state["selected_ticker"] = xrow["ticker"]
            st.session_state["selected_row"] = xrow
            st.session_state["total_portfolio_value"] = total_portfolio_value
            st.session_state["scroll_to_top_detail"] = _scroll
            st.rerun()
        st.query_params.pop("detail", None)
        st.rerun()


def sync_table_selection():
    """Randul ales intr-un tabel (pozitii sau watchlist) la rularea anterioara devine pozitia deschisa."""
    _tbl_state = st.session_state.get(f"positions_table_{st.session_state.get('table_nonce', 0)}")
    _tbl_rows = []
    if _tbl_state:
        try:
            _tbl_rows = list(_tbl_state["selection"]["rows"])
        except Exception:
            _tbl_rows = []
    _cached_rows = st.session_state.get("_table_rows")
    if _tbl_rows and _cached_rows and "selected_ticker" not in st.session_state and _tbl_rows[0] < len(_cached_rows):
        _row = _cached_rows[_tbl_rows[0]]
        st.session_state["selected_ticker"] = _row["ticker"]
        st.session_state["selected_row"] = _row
        st.session_state["total_portfolio_value"] = st.session_state.get("_table_total", 0)
        st.session_state["scroll_to_top_detail"] = True

    _wl_state = st.session_state.get(f"watchlist_table_{st.session_state.get('table_nonce', 0)}")
    _wl_rows = []
    if _wl_state:
        try:
            _wl_rows = list(_wl_state["selection"]["rows"])
        except Exception:
            _wl_rows = []
    _wl_cached = st.session_state.get("_watch_rows")
    if _wl_rows and _wl_cached and "selected_ticker" not in st.session_state and _wl_rows[0] < len(_wl_cached):
        _wrow = _wl_cached[_wl_rows[0]]
        st.session_state["selected_ticker"] = _wrow["ticker"]
        st.session_state["selected_row"] = _wrow
        st.session_state["total_portfolio_value"] = st.session_state.get("_table_total", 0)
        st.session_state["scroll_to_top_detail"] = True


def sync_page_and_url():
    """?page=settings si ?detail= raman in acord cu starea sesiunii (refresh-ul pastreaza pagina)."""
    # ?page=settings e sursa de adevar, ca refresh-ul sa ramana pe Setari
    if st.query_params.get("page") == "settings":
        st.session_state["_page"] = "settings"
    elif st.session_state.get("_page") == "settings":
        st.session_state.pop("_page", None)

    _url_detail = st.query_params.get("detail")
    _sel = st.session_state.get("selected_ticker")
    _synced = st.session_state.get("_url_ticker")
    if _sel is not None:
        if _synced != _sel:
            st.query_params["detail"] = str(_sel)
            st.session_state["_url_ticker"] = _sel
        elif _url_detail != str(_sel):
            for _k in ("selected_ticker", "selected_row", "_url_ticker"):
                st.session_state.pop(_k, None)
            st.session_state["scroll_to_top_main"] = True
            st.session_state["table_nonce"] = st.session_state.get("table_nonce", 0) + 1
    elif _synced is not None:
        st.session_state.pop("_url_ticker", None)
        if _url_detail is not None:
            st.query_params.pop("detail", None)
