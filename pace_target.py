"""Tinta de ritm lunar (depuneri nete / luna), setata de utilizator in Setari > Obiective;
colorarea badge-ului de ritm de sub Total investit dupa cat din tinta e atins."""
import streamlit as st

from i18n import t
from lang_prefs import load_pref, save_pref

PREF_KEY = "pace_target"
# (pragul minim din tinta, culoare): verde de la 100%, galben 90-100%, portocaliu 75-90%, rosu sub 75%
LEVELS = ((1.0, "#21c354"), (0.9, "#e8c547"), (0.75, "#eb8c34"), (0.0, "#ff4b4b"))


def load():
    """(suma, moneda) sau None daca nu e setata."""
    v = load_pref(PREF_KEY)
    try:
        amount = float(v["amount"])
        return (amount, str(v["ccy"])) if amount > 0 else None
    except Exception:
        return None


def color_for(pace, target):
    """Culoarea badge-ului pentru ritmul dat fata de tinta (aceeasi moneda)."""
    ratio = pace / target if target else 1.0
    return next(c for lim, c in LEVELS if ratio >= lim)


def badge_css(container_key, color):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    sel = ".st-key-%s [data-testid=\"stMetricDelta\"]" % container_key
    return ("<style>%s{background-color:rgba(%d,%d,%d,0.22)!important;color:%s!important}"
            "%s *{color:%s!important}</style>" % (sel, r, g, b, color, sel, color))


def render_settings_section(currencies, default_ccy):
    st.markdown("**" + t("pace.title") + "**")
    st.caption(t("pace.help"))
    cur = load()
    ccys = list(currencies)
    ccy0 = cur[1] if cur else default_ccy
    if ccy0 not in ccys:
        ccys.insert(0, ccy0)
    c1, c2 = st.columns([3, 1])
    amount = c1.number_input(t("pace.amount"), min_value=0.0, step=50.0, value=cur[0] if cur else 0.0,
                             key="pace_target_amount", format="%.2f")
    ccy = c2.selectbox(t("pace.ccy"), ccys, index=ccys.index(ccy0), key="pace_target_ccy")
    new = {"amount": float(amount), "ccy": ccy} if amount > 0 else None
    if new != (load_pref(PREF_KEY) or None):
        save_pref(PREF_KEY, new)
        st.toast(t("pace.saved"))
