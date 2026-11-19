"""Tab-ul Calendar din pagina principala si sectiunea Calendar din Setari."""
import pandas as pd
import streamlit as st

import events
import notify
import users
from i18n import t

RANGES = (7, 14, 30, 60)
ICONS = {"earnings": "📊", "ex_dividend": "✂️", "dividend_payment": "💰"}


def _short_date(iso, today_year):
    """05.12 (sau 05.12.2027 daca e in alt an decat cel curent)."""
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}" + (f".{y}" if int(y) != today_year else "")


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
        import html_table
        import logos
        from datetime import date as _date
        year = _date.today().year
        logos.prefetch([(ev["ticker"], names.get(ev["ticker"]) or "") for ev in rows])
        cols = [{"key": "date", "label": t("ev.col.date"), "width": "1%", "nowrap": True},
                {"key": "days", "label": t("ev.col.days_short"), "help": t("ev.col.days"), "width": "1%", "align": "right", "nowrap": True},
                {"key": "logo", "label": "", "width": "30px"},
                {"key": "name", "label": t("ev.col.name")},
                {"key": "type", "label": t("ev.col.type"), "nowrap": True},
                {"key": "detail", "label": t("ev.col.detail")}]
        out = []
        for ev in rows:
            name = names.get(ev["ticker"]) or ev["ticker"]
            when = _short_date(ev["date"], year) + ("–" + _short_date(ev["date_end"], year) if ev.get("date_end") else "")
            out.append({
                "date": {"text": when, "title": ev["date"] + (" – " + ev["date_end"] if ev.get("date_end") else "")},
                "days": ev["days"],
                "logo": {"img": logos.logo_uri(ev["ticker"], name), "img_title": ev["ticker"]},
                "name": {"text": name, "title": ev["ticker"], "href": html_table.detail_href(ev["ticker"])},
                "type": {"text": ICONS.get(ev["type"], "•") + " " + t("ev.type." + ev["type"]), "title": t("ev.desc." + ev["type"])},
                "detail": t("ev.eps_est", v="%.2f" % ev["eps_avg"]) if ev.get("eps_avg") is not None else "",
            })
        html_table.render(cols, out)
    with st.expander(t("ev.legend")):
        for k in events.TYPES:
            st.markdown(f"{ICONS.get(k, '•')} **{t('ev.type.' + k)}** — {t('ev.desc.' + k)}")
        st.caption(t("ev.legend_hint"))
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
    b1, b2 = st.columns([1, 3])
    if b1.button(t("set.ev_save"), key="ev_set_save"):
        if users.set_email(me, mail):
            st.error(t("set.ev_bad_email"))
        else:
            events.save_prefs(enabled, days)
            st.success(t("set.ev_saved"))
    email = users.email(me)
    if b2.button(t("ev.test_send"), key="ev_test_send", disabled=not (email and notify.configured())):
        with st.spinner("…"):
            ok = events.send_test(me)
        if ok:
            st.success(t("ev.test_sent", email=email))
        else:
            st.error(t("ev.test_not_sent"))
