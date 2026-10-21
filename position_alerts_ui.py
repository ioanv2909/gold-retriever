"""Setari -> Alerte, bannerul din pagina principala si alerta rapida de pret din pagina pozitiei."""
import time

import streamlit as st

import position_alerts as pa
from i18n import lang, t

BANNER_MAX = 3
BANNER_DAYS = 30


@st.cache_data(ttl=300, show_spinner=False)
def cached_holdings(user):
    return pa.current_holdings()[0]


def _when(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""


def render_banner():
    cutoff = time.time() - BANNER_DAYS * 86400
    unseen = [e for e in pa.load_log() if not e.get("seen") and e.get("ts", 0) >= cutoff]
    if not unseen:
        return
    for e in reversed(unseen[-BANNER_MAX:]):
        c1, c2 = st.columns([8, 1], vertical_alignment="center")
        c1.warning("🔔 " + pa.describe(e, lang()))
        if c2.button(t("pa.banner_seen"), key="pa_seen_%s_%s" % (e["ts"], e["ticker"])):
            pa.dismiss(e["ts"])
            st.rerun()
    if len(unseen) > 1 and st.button(t("pa.banner_all_seen"), key="pa_seen_all"):
        pa.dismiss()
        st.rerun()


def _price_section(holdings):
    st.markdown("#### " + t("pa.price_title"))
    st.caption(t("pa.price_hint"))
    rules = pa.load_rules()
    tickers = sorted(holdings, key=lambda k: (holdings[k].get("name") or k).casefold())
    if tickers:
        c1, c2, c3, c4 = st.columns([4, 3, 2, 2], vertical_alignment="bottom")
        ticker = c1.selectbox(t("pa.ticker"), tickers, key="pa_ticker",
                              format_func=lambda k: "%s (%s)" % (holdings[k].get("name") or k, k))
        op = c2.selectbox(t("pa.op"), ("above", "below"), key="pa_op", format_func=lambda o: t("pa.op." + o))
        h = holdings.get(ticker) or {}
        price = c3.number_input(t("pa.price"), min_value=0.0, value=float(h.get("price") or 0.0), step=0.01,
                                format="%.2f", key="pa_price_" + ticker)
        if c4.button(t("pa.add"), key="pa_add"):
            if pa.add_price_alert(ticker, op, price, h.get("name"), h.get("ccy")):
                st.success(t("pa.added"))
                st.rerun()
            else:
                st.error(t("pa.bad_price"))
        if h.get("price") is not None:
            c3.caption(t("pa.current", p="%.2f %s" % (h["price"], h.get("ccy") or "")))
    if not rules["price"]:
        st.caption(t("pa.none"))
    for a in rules["price"]:
        c1, c2, c3 = st.columns([7, 2, 1], vertical_alignment="center")
        status = t("pa.active") if a.get("active") else t("pa.fired", d=_when(a.get("triggered_at")))
        c1.markdown("**%s** (%s) · %s %.2f %s · _%s_" % (
            a.get("name") or a["ticker"], a["ticker"], t("pa.op." + a["op"]), a["price"], a.get("ccy") or "", status))
        if not a.get("active") and c2.button(t("pa.rearm"), key="pa_rearm_" + a["id"]):
            pa.rearm_price_alert(a["id"])
            st.rerun()
        if c3.button(t("pa.delete"), key="pa_del_" + a["id"]):
            pa.remove_price_alert(a["id"])
            st.rerun()


def _score_section():
    st.markdown("#### " + t("pa.score_title"))
    rule = pa.load_rules()["score"]
    on = st.checkbox(t("pa.score_enable"), value=rule["enabled"], key="pa_s_on")
    kinds = st.multiselect(t("pa.score_kinds"), pa.SCORE_KINDS, default=rule["kinds"],
                           format_func=lambda k: t("pa.kind." + k), key="pa_s_kinds")
    c1, c2 = st.columns(2)
    below = c1.number_input(t("pa.score_below"), 0, 100, int(rule["below"]), key="pa_s_below")
    drop = c2.number_input(t("pa.score_drop"), 1, 100, int(rule["drop"]), key="pa_s_drop")
    if st.button(t("pa.save"), key="pa_s_save"):
        pa.save_score_rule(on, kinds, below, drop)
        st.success(t("pa.saved"))


def _concentration_section():
    st.markdown("#### " + t("pa.conc_title"))
    rule = pa.load_rules()["concentration"]
    on = st.checkbox(t("pa.conc_enable"), value=rule["enabled"], key="pa_c_on")
    max_pct = st.number_input(t("pa.conc_max"), 1.0, 100.0, float(rule["max_pct"]), step=1.0, key="pa_c_max")
    st.caption(t("pa.conc_hint"))
    if st.button(t("pa.save"), key="pa_c_save"):
        pa.save_concentration_rule(on, max_pct)
        st.success(t("pa.saved"))


def _events_section():
    st.markdown("#### " + t("pa.ev_title"))
    rule = pa.load_rules()["events"]
    on = st.checkbox(t("pa.ev_enable"), value=rule["enabled"], key="pa_e_on")
    st.caption(t("pa.ev_hint"))
    if st.button(t("pa.save"), key="pa_e_save"):
        pa.save_events_rule(on)
        st.success(t("pa.saved"))


def render_settings_section(me):
    st.caption(t("pa.caption"))
    _price_section(cached_holdings(me))
    st.divider()
    _score_section()
    st.divider()
    _concentration_section()
    st.divider()
    _events_section()
    log = pa.load_log()
    if log:
        st.divider()
        st.markdown("#### " + t("pa.log_title"))
        for e in reversed(log[-20:]):
            st.caption("%s · %s" % (_when(e.get("ts")), pa.describe(e, lang())))


def render_quick_price_alert(ticker, name, price, ccy):
    """Expander in pagina pozitiei: adauga o alerta de pret pentru tickerul curent."""
    with st.expander(t("pa.quick_title")):
        mine = [a for a in pa.load_rules()["price"] if a.get("ticker") == ticker]
        for a in mine:
            status = t("pa.active") if a.get("active") else t("pa.fired", d=_when(a.get("triggered_at")))
            st.caption("%s %.2f %s · %s" % (t("pa.op." + a["op"]), a["price"], a.get("ccy") or "", status))
        c1, c2, c3 = st.columns([3, 2, 2], vertical_alignment="bottom")
        op = c1.selectbox(t("pa.op"), ("above", "below"), key="pa_q_op_" + ticker, format_func=lambda o: t("pa.op." + o))
        target = c2.number_input(t("pa.price"), min_value=0.0, value=float(price or 0.0), step=0.01,
                                 format="%.2f", key="pa_q_price_" + ticker)
        if c3.button(t("pa.add"), key="pa_q_add_" + ticker):
            if pa.add_price_alert(ticker, op, target, name, ccy):
                st.success(t("pa.added"))
            else:
                st.error(t("pa.bad_price"))
