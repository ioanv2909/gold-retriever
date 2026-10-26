"""Setari -> Utilizatori -> Sesiuni (doar admini): limitele de expirare a sesiunilor."""
import streamlit as st

import alerts
import session_policy as sp
from i18n import t


def render_session_policy(me):
    idle, days = sp.limits()
    st.caption(t("sess.help"))
    with st.form("session_policy_form"):
        new_idle = st.number_input(t("sess.idle", d=sp.DEFAULT_IDLE_HOURS), min_value=sp.IDLE_RANGE[0],
                                   max_value=sp.IDLE_RANGE[1], value=idle, step=1)
        new_days = st.number_input(t("sess.max", d=sp.DEFAULT_MAX_DAYS), min_value=sp.MAX_DAYS_RANGE[0],
                                   max_value=sp.MAX_DAYS_RANGE[1], value=days, step=1)
        c1, c2 = st.columns(2)
        save = c1.form_submit_button(t("sess.save"))
        reset = c2.form_submit_button(t("sess.reset"))
    if not (save or reset):
        return
    if reset:
        sp.reset_limits()
        err = None
    else:
        err = sp.save_limits(int(new_idle), int(new_days))
    if err:
        st.error(t("sess.err_" + err))
        return
    n_idle, n_days = sp.limits()
    if (n_idle, n_days) != (idle, days):
        try:
            alerts.record_user_event("politica sesiunilor schimbata", me, "toti utilizatorii",
                                     "inactivitate %s h -> %s h, durata maxima %s zile -> %s zile" % (idle, n_idle, days, n_days))
        except Exception:
            pass
    st.success(t("sess.saved", h=n_idle, d=n_days))
