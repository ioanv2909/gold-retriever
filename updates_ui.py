"""Settings > Updates: butoanele de actualizare (Trading 212, dividende, recomandari)."""
import streamlit as st

import autorefresh
from background import (load_dividends_status, load_ratings_status, start_dividends_fetch_background,
                        start_quality_fetch_background, start_ratings_fetch_background, xtb_tickers as _xtb_tickers)
from core import load_config
from i18n import t
from t212_api import fetch_and_cache_core, load_cached_snapshot


def render_updates_section(api_key_id, api_secret, interval_minutes):
    """Settings > Updates: refresh buttons (moved out of the sidebar)."""
    if api_key_id and api_secret:
        st.caption(t("side.auto_on", n=interval_minutes))
    else:
        st.caption(t("side.auto_off"))
    autorefresh.render_settings_toggle()
    div_status = load_dividends_status()
    rat_status = load_ratings_status()
    if st.button(t("btn.refresh_now"), key="upd_now"):
        disk_cfg = load_config()
        fetch_and_cache_core(disk_cfg.get("api_key_id"), disk_cfg.get("api_secret"))
        st.rerun()
    if div_status.get("in_progress"):
        st.button(t("btn.refresh_div_busy"), disabled=True, key="div_btn_busy")
    elif st.button(t("btn.refresh_div"), key="upd_div"):
        disk_cfg = load_config()
        snap_now = load_cached_snapshot()
        tickers_now = [x.get("ticker") for x in (snap_now.get("positions") or [])] if snap_now else []
        if start_dividends_fetch_background(disk_cfg.get("api_key_id"), disk_cfg.get("api_secret"), tickers_now):
            st.rerun()
    if rat_status.get("in_progress"):
        st.button(t("btn.refresh_rat_busy"), disabled=True, key="rat_btn_busy")
    elif st.button(t("btn.refresh_rat"), key="upd_rat"):
        snap_now = load_cached_snapshot()
        tickers_now = [x.get("ticker") for x in (snap_now.get("positions") or [])] if snap_now else []
        _all_now = list(tickers_now) + [x for x in _xtb_tickers() if x not in tickers_now]
        start_quality_fetch_background(_all_now)
        if start_ratings_fetch_background(_all_now):
            st.rerun()
