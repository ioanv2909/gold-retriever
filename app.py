import logwatch
logwatch.install()  # inainte de orice alt import, ca sa prinda tot ce se scrie in log
import streamlit as st
import os

from background import start_background_scheduler
from core import load_config
from detail_view import render_detail_view
from i18n import install_translation, t
import lang_prefs

install_translation()
lang_prefs.restore_lang()

st.set_page_config(page_title="GoldRetriever", layout="wide", page_icon="assets/icon-192.png" if os.path.exists("assets/icon-192.png") else "🐕")

os.makedirs("data", exist_ok=True)

import appearance
appearance.hide_streamlit_header()

import users as _users
from auth import require_login
for _u in _users.names():
    start_background_scheduler(_u)
_me = require_login()
for _u in _users.names():
    start_background_scheduler(_u)
lang_prefs.apply_user_lang(_me)
if st.session_state.get("_page_users"):
    from auth import render_users_page as _render_users_page
    _render_users_page(_me)
    st.stop()


config_data = load_config()
api_key_id = config_data.get("api_key_id", "")
api_secret = config_data.get("api_secret", "")
interval_minutes = int(config_data.get("interval_minutes", 15))

import autorefresh
import mobile
import navigation
import privacy

navigation.sync_table_selection()
navigation.sync_page_and_url()

mobile.inject_css()
if "selected_ticker" in st.session_state and "selected_row" in st.session_state:
    render_detail_view(st.session_state["selected_row"], st.session_state.get("total_portfolio_value", 0), api_key_id, api_secret)
    autorefresh.watch(detail=True)
else:
    if st.session_state.get("_page") == "settings" and mobile.compact():
        # pe telefon doar aspectul (tema se tine separat in fiecare browser); restul pe desktop
        appearance.render_settings_section()
        st.divider()
        st.info(t("mob.settings_desktop"))
        if st.button(t("mob.full"), key="settings_full_view"):
            mobile.set_mode("full")
            st.rerun()
        if st.button(t("dv.back"), key="settings_mobile_back"):
            st.session_state.pop("_page", None)
            st.query_params.pop("page", None)
            st.rerun()
        st.stop()
    if st.session_state.get("_page") == "settings":
        from settings_page import render_settings
        from events_ui import render_settings_section as _events_settings
        from position_alerts_ui import render_settings_section as _alerts_settings
        from updates_ui import render_updates_section
        from weekly_report_ui import render_settings_section as _weekly_settings
        from xtb_import_ui import render_xtb_import
        render_settings(_me, [("updates", t("side.updates"), lambda: render_updates_section(api_key_id, api_secret, interval_minutes)),
                              ("xtb", t("side.xtb_import"), lambda: render_xtb_import(_me)),
                              ("calendar", t("set.events"), lambda: _events_settings(_me)),
                              ("alerts", t("set.alerts"), lambda: _alerts_settings(_me)),
                              ("weekly", t("wr.tab"), lambda: _weekly_settings(_me)),
                              ("privacy", t("priv.tab"), privacy.render_settings_section),
                              ("appearance", t("app.tab"), appearance.render_settings_section)])
        st.stop()
    from main_view import render_main_view
    render_main_view(_me, api_key_id, api_secret)
    autorefresh.watch()
