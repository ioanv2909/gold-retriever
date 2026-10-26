"""Setari -> Log (admin): ultimele linii scrise de aplicatie pe stdout/stderr, tinute in memorie de logwatch."""
import time

import streamlit as st

import logwatch
from i18n import t

SIZES = (100, 300, 1000)


def render_log(me):
    st.caption(t("lg.caption", n=logwatch.TAIL))
    c1, c2, c3, c4, c5 = st.columns([2, 3, 4, 3, 2], vertical_alignment="bottom")
    n = c1.selectbox(t("lg.lines"), SIZES, index=1, key="lg_n")
    order = c2.selectbox(t("lg.order"), ("desc", "asc"), format_func=lambda o: t("lg.order_" + o), key="lg_order")
    query = c3.text_input(t("lg.filter"), key="lg_q")
    hide = c4.checkbox(t("lg.hide_noise"), value=True, key="lg_hide")
    if c5.button(t("lg.refresh"), key="lg_refresh"):
        st.rerun()
    lines = logwatch.tail(n, hide_noise=hide, query=query.strip(), newest_first=order == "desc")
    if not lines:
        st.info(t("lg.empty"))
        return
    text = "\n".join(lines)
    st.caption(t("lg.shown", n=len(lines)))
    st.code(text, language=None, line_numbers=False, wrap_lines=True, height=600)
    st.download_button(t("lg.download"), text, file_name=time.strftime("goldretriever-log-%Y%m%d-%H%M.txt"),
                       mime="text/plain", key="lg_dl")
