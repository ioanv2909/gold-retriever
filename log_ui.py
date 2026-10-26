"""Setari -> Log (admin): ultimele linii scrise de aplicatie pe stdout/stderr, tinute in memorie de logwatch."""
import time

import streamlit as st

import logwatch
from i18n import t

SIZES = (100, 300, 1000)


def render_log(me):
    st.caption(t("lg.caption", n=logwatch.TAIL))
    c1, c2, c3, c4 = st.columns([2, 4, 3, 2], vertical_alignment="bottom")
    n = c1.selectbox(t("lg.lines"), SIZES, index=1, key="lg_n")
    query = c2.text_input(t("lg.filter"), key="lg_q")
    hide = c3.checkbox(t("lg.hide_noise"), value=True, key="lg_hide")
    if c4.button(t("lg.refresh"), key="lg_refresh"):
        st.rerun()
    lines = logwatch.tail(n, hide_noise=hide, query=query.strip())
    if not lines:
        st.info(t("lg.empty"))
        return
    text = "\n".join(lines)
    st.caption(t("lg.shown", n=len(lines)))
    st.code(text, language=None, line_numbers=False, wrap_lines=True, height=600)
    st.download_button(t("lg.download"), text, file_name=time.strftime("goldretriever-log-%Y%m%d-%H%M.txt"),
                       mime="text/plain", key="lg_dl")
