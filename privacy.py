"""Modul de confidentialitate: sumele (valori, cost, P/L, dividende, numerar) se ascund, procentele raman.
Setarea per utilizator decide starea la deschiderea sesiunii; butonul 👁 le arata/ascunde in sesiune."""
import streamlit as st

from core import load_json_file, save_json_file
from userctx import UPath

PRIVACY_FILE = UPath("privacy.json")
MASK = "•••••"
_KEY = "_amounts_hidden"


def load_setting():
    return bool(load_json_file(PRIVACY_FILE, {}).get("hide_on_start", False))


def save_setting(hide_on_start):
    save_json_file(PRIVACY_FILE, {"hide_on_start": bool(hide_on_start)})


def hidden():
    try:
        if _KEY not in st.session_state:
            st.session_state[_KEY] = load_setting()
        return bool(st.session_state[_KEY])
    except Exception:
        return False  # in afara unei sesiuni Streamlit (fundal, email) sumele nu se ascund


def mask(text):
    """Textul unei sume, sau MASK cand sumele sunt ascunse."""
    return MASK if hidden() else text


def toggle_button(key):
    from i18n import t
    if st.button("👁 " + t("priv.show") if hidden() else "🙈 " + t("priv.hide"), key=key, type="tertiary"):
        st.session_state[_KEY] = not hidden()
        st.rerun()


def render_settings_section():
    from i18n import t
    st.markdown("**" + t("priv.title") + "**")
    on = st.toggle(t("priv.on_start"), value=load_setting(), key="privacy_on_start", help=t("priv.help"))
    if on != load_setting():
        save_setting(on)
        st.session_state[_KEY] = on
        st.toast(t("priv.saved"))
