"""Tab-ul Calendar din pagina principala si sectiunea Calendar din Setari."""
import pandas as pd
import streamlit as st

import events
import notify
import users
from i18n import t

RANGES = (7, 14, 30, 60)


def render_calendar_tab(names):
    """names: dict ticker -> nume, pentru pozitiile afisate."""
    tickers = list(names)
    status = events.load_status()
    cache = events.load_cache()
    if status.get("in_progress"):
        st.caption(t("ev.loading", done=status.get("done", 0), total=status.get("total", 0)))

    c1, c2, c3 = st.columns([2, 5, 2], vertical_alignment="bottom")
    days = c1.selectbox(t("ev.range"), RANGES, index=2, format_func=lambda n: t("ev.range_days", n=n), key="ev_range")
    kinds = c2.multiselect(t("ev.filter_types"), events.TYPES, default=list(events.TYPES),
                           format_func=lambda k: t("ev.type." + k), key="ev_types")
    if c3.button(t("ev.refresh"), key="ev_refresh", disabled=bool(status.get("in_progress"))):
        missing = [tk for tk in tickers if tk not in cache]
        events.start_events_fetch_background(missing or tickers)
        st.rerun()

    rows = [ev for ev in events.upcoming(cache, tickers, days=days) if ev["type"] in kinds]
    if not rows:
        st.info(t("ev.empty"))
    else:
        df = pd.DataFrame([{
            t("ev.col.date"): ev["date"] + (" – " + ev["date_end"] if ev.get("date_end") else ""),
            t("ev.col.days"): ev["days"],
            t("ev.col.ticker"): ev["ticker"],
            t("ev.col.name"): names.get(ev["ticker"]) or "",
            t("ev.col.type"): t("ev.type." + ev["type"]),
            t("ev.col.detail"): t("ev.eps_est", v="%.2f" % ev["eps_avg"]) if ev.get("eps_avg") is not None else "",
        } for ev in rows])
        st.dataframe(df, hide_index=True, width="stretch")
    st.caption(t("ev.source"))


def render_settings_section(me):
    st.caption(t("set.ev_caption"))
    prefs = events.load_prefs()
    mail = st.text_input(t("set.ev_email"), value=users.email(me) or "", key="ev_set_mail",
                         placeholder="name@example.com")
    enabled = st.checkbox(t("set.ev_enable"), value=prefs["email"], key="ev_set_on")
    days = st.number_input(t("set.ev_days"), min_value=1, max_value=30, value=int(prefs["days_ahead"]), key="ev_set_days")
    if not notify.configured():
        st.caption(t("set.ev_no_smtp"))
    if st.button(t("set.ev_save"), key="ev_set_save"):
        if users.set_email(me, mail):
            st.error(t("set.ev_bad_email"))
        else:
            events.save_prefs(enabled, days)
            st.success(t("set.ev_saved"))
