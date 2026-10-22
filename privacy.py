"""Modul de confidentialitate: sumele (valori, cost, P/L, dividende, numerar) se ascund, procentele raman.
Setarea per utilizator (separat pentru telefon si desktop) decide starea la deschiderea sesiunii;
butonul 👁 le arata/ascunde in sesiune."""
import streamlit as st

from core import load_json_file, save_json_file
from userctx import UPath

PRIVACY_FILE = UPath("privacy.json")
MASK = "•••••"
_KEY = "_amounts_hidden"


DEVICES = ("phone", "desktop")


def load_setting(device):
    data = load_json_file(PRIVACY_FILE, {})
    # "hide_on_start" e formatul vechi, comun pentru ambele dispozitive
    return bool(data.get("hide_on_start_" + device, data.get("hide_on_start", False)))


def save_setting(device, hide_on_start):
    data = {"hide_on_start_" + d: load_setting(d) for d in DEVICES}
    data["hide_on_start_" + device] = bool(hide_on_start)
    save_json_file(PRIVACY_FILE, data)


def _device():
    import mobile
    return "phone" if mobile.compact() else "desktop"


def hidden():
    try:
        if _KEY not in st.session_state:
            st.session_state[_KEY] = load_setting(_device())
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
    st.caption(t("priv.help"))
    for device in DEVICES:
        on = st.toggle(t("priv.on_start_" + device), value=load_setting(device), key="privacy_on_start_" + device)
        if on != load_setting(device):
            save_setting(device, on)
            if device == _device():
                st.session_state[_KEY] = on
            st.toast(t("priv.saved"))
