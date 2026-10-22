"""Aspect: fara bara de sus a Streamlit (activitate, meniul cu trei puncte); tema se alege din Setari,
tiparirea din meniul utilizatorului."""
import time

import streamlit as st

THEMES = ("System", "Light", "Dark")

_CSS = """<style>
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none !important;}
[data-testid="stMainBlockContainer"], .block-container {padding-top: 1rem !important;}
</style>"""


def hide_streamlit_header():
    st.markdown(_CSS, unsafe_allow_html=True)


def _run_js(body):
    # nonce: fiecare apel e un element nou, deci scriptul ruleaza din nou
    st.html("<script>// " + str(time.time()) + "\n" + body + "</script>", unsafe_allow_javascript=True)


def print_page():
    """Inchide popover-ul deschis (Escape) si deschide dialogul de tiparire al browserului."""
    _run_js("""
var w = window.parent || window;
w.document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
setTimeout(function () { w.print(); }, 400);
""")


def _apply_theme(name):
    # aceeasi cheie in care meniul Streamlit isi tine tema; se citeste la incarcarea paginii
    _run_js("""
var w = window.parent || window;
w.localStorage.setItem('stActiveTheme-' + w.location.pathname + '-v2', JSON.stringify(%r));
w.location.reload();
""" % name)


def render_settings_section():
    from i18n import t
    st.markdown("**" + t("app.theme") + "**")
    try:
        current = st.context.theme.type
    except Exception:
        current = None
    if current:
        st.caption(t("app.theme_now", th=t("app.theme." + current)))
    cols = st.columns(len(THEMES))
    for col, name in zip(cols, THEMES):
        if col.button(t("app.theme." + name.lower()), key="theme_" + name, width="stretch"):
            _apply_theme(name)
    st.caption(t("app.theme_help"))
