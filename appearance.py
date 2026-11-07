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


_STICKY_CSS = """<style>
/* bara de sus fixa (ca in AstroLibrary): titlul, limba si meniul raman vizibile la derulare */
[data-testid="stLayoutWrapper"]:has(> .st-key-%(k)s),
[data-testid="stElementContainer"]:has(> .st-key-%(k)s),
.st-key-%(k)s {
    position: sticky; top: 0; z-index: 999;
}
.st-key-%(k)s {
    background: color-mix(in srgb, var(--gr-bg, #0e1117) 90%%, transparent);
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid color-mix(in srgb, var(--gr-fg, #fafafa) 14%%, transparent);
    padding: 0.35rem 0 0.35rem 0;
}
.st-key-%(k)s h1 {padding: 0 !important; margin: 0 !important; line-height: 1.15;}
.st-key-%(k)s img {transition: width 0.2s;}
@keyframes gr-hdr-title {from {font-size: 2.6rem;} to {font-size: 1.5rem;}}
@keyframes gr-hdr-logo {from {width: 64px;} to {width: 40px;}}
@supports (animation-timeline: scroll()) {
    .st-key-%(k)s h1 {animation: gr-hdr-title linear both; animation-timeline: scroll(nearest); animation-range: 0px 160px;}
    .st-key-%(k)s img.gr-logo {animation: gr-hdr-logo linear both; animation-timeline: scroll(nearest); animation-range: 0px 160px;}
}
</style>"""

# culorile temei curente (Streamlit nu le expune ca variabile CSS): fundalul si textul aplicatiei
_THEME_VARS_JS = """
var w = window.parent || window, d = w.document, app = d.querySelector('[data-testid="stApp"]') || d.body;
var cs = w.getComputedStyle(app);
d.documentElement.style.setProperty('--gr-bg', cs.backgroundColor);
d.documentElement.style.setProperty('--gr-fg', cs.color);
"""


def sticky_header(key):
    """Containerul cu cheia `key` devine bara de sus fixa, cu fundalul temei (deschisa sau inchisa)."""
    st.markdown(_STICKY_CSS % {"k": key}, unsafe_allow_html=True)
    _run_js(page_js())


def page_js():
    """Scriptul rulat o data pe pagina: culorile temei pentru bara fixa + axa Y automata la graficele trase."""
    import chart_window
    return _THEME_VARS_JS + chart_window.Y_AUTO_JS


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
