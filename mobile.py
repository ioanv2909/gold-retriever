"""Versiunea compacta pentru telefon: aceeasi aplicatie, cu mai putine informatii pe ecran.
Telefonul se detecteaza dupa User-Agent; ?view=compact / ?view=full fixeaza alegerea pentru sesiune."""
import re

import streamlit as st

PARAM = "view"
_KEY = "_view_mode"
_MOBILE_UA = re.compile(r"Mobi|Android|iPhone|iPod|Windows Phone", re.I)

_CSS = """<style>
[data-testid="stMainBlockContainer"], .block-container {padding-left: 0.75rem !important; padding-right: 0.75rem !important;}
[class*="st-key-mobhide_"],
[data-testid="stElementContainer"]:has(> [class*="st-key-mobhide_"]),
[data-testid="stLayoutWrapper"]:has(> [class*="st-key-mobhide_"]) {display: none !important;}
.st-key-app_header [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: 0.5rem;}
.st-key-app_header [data-testid="stColumn"] {min-width: 0 !important; width: auto !important; flex: 0 1 auto !important;}
.st-key-app_header [data-testid="stColumn"]:nth-child(2) {flex: 1 1 auto !important;}
.st-key-app_header h1 {font-size: 1.2rem !important; padding: 0 !important;}
.st-key-app_header img {width: 36px !important;}
.st-key-summary_metrics [data-testid="stHorizontalBlock"] {flex-wrap: wrap !important;}
.st-key-summary_metrics [data-testid="stColumn"] {flex: 1 1 45% !important; min-width: 45% !important;}
[data-testid="stMetricValue"] {font-size: 1.3rem;}
</style>"""


def is_mobile_ua(user_agent):
    return bool(_MOBILE_UA.search(user_agent or ""))


def compact():
    """True pe telefon sau cu ?view=compact; ?view=full forteaza versiunea completa."""
    wanted = st.query_params.get(PARAM)
    if wanted in ("compact", "full"):
        st.session_state[_KEY] = wanted
    mode = st.session_state.get(_KEY)
    if mode:
        return mode == "compact"
    try:
        ua = st.context.headers.get("User-Agent", "")
    except Exception:
        ua = ""
    return is_mobile_ua(ua)


def set_mode(mode):
    st.session_state[_KEY] = mode
    st.query_params[PARAM] = mode


def inject_css():
    if compact():
        st.markdown(_CSS, unsafe_allow_html=True)


def desktop_only(key):
    """Container ascuns pe telefon (codul ruleaza in continuare, ca variabilele calculate inauntru sa existe)."""
    return st.container(key=("mobhide_" if compact() else "desk_") + key)
