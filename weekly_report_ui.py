"""Setari -> Raport saptamanal: activare, zi si ora, previzualizare si trimitere de test."""
from datetime import datetime

import streamlit as st

import notify
import users
import weekly_report
from i18n import t


def render_settings_section(me):
    st.caption(t("wr.caption"))
    prefs = weekly_report.load_prefs()
    days = t("wr.days").split(",")
    c1, c2, c3 = st.columns([3, 2, 2])
    enabled = c1.checkbox(t("wr.enable"), value=prefs["enabled"], key="wr_on")
    weekday = c2.selectbox(t("wr.weekday"), range(7), index=prefs["weekday"], format_func=lambda i: days[i], key="wr_day")
    hour = c3.number_input(t("wr.hour"), min_value=0, max_value=23, value=int(prefs["hour"]), key="wr_hour")
    email = users.email(me)
    if not email:
        st.warning(t("wr.no_email"))
    if not notify.configured():
        st.caption(t("wr.no_smtp"))
    state = weekly_report._load_state()
    if state.get("sent_at"):
        st.caption(t("wr.last", ts=datetime.fromisoformat(state["sent_at"]).strftime("%d.%m.%Y %H:%M")))
    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button(t("wr.save"), key="wr_save"):
        weekly_report.save_prefs(enabled, weekday, hour)
        st.success(t("wr.saved"))
    if b2.button(t("wr.preview"), key="wr_preview"):
        with st.spinner("…"):
            _subject, body, _totals = weekly_report.build(st.session_state.get("lang", "RO"))
        st.code(body, language=None)
    if b3.button(t("wr.send_now"), key="wr_send", disabled=not (email and notify.configured())):
        with st.spinner("…"):
            ok = weekly_report.send(me, mark=False)
        if ok:
            st.success(t("wr.sent", email=email))
        else:
            st.error(t("wr.not_sent"))
