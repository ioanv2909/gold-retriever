"""Tinta de ritm lunar (depuneri nete / luna), setata de utilizator in Setari > Obiective;
colorarea badge-ului de ritm de sub Total investit dupa cat din tinta e atins."""
import streamlit as st

from core import load_json_file, save_json_file
from i18n import t
from lang_prefs import load_pref, save_pref
from userctx import UPath

PREF_KEY = "pace_target"
# (pragul minim din tinta, culoare): verde de la 100%, galben 90-100%, portocaliu 75-90%, rosu sub 75%
LEVELS = ((1.0, "#21c354"), (0.9, "#e8c547"), (0.75, "#eb8c34"), (0.0, "#ff4b4b"))
PACE_MIN_EUR = 50.0
CHECK_INTERVAL = 3600
# emailul pleaca doar sub 95% din tinta (nu in fiecare luna, chiar inainte de alimentare); se rearmeaza la 100%
EMAIL_MARGIN = 0.95
STATE_FILE = UPath("pace_alert_state.json")


def load():
    """(suma, moneda) sau None daca nu e setata."""
    v = load_pref(PREF_KEY)
    try:
        amount = float(v["amount"])
        return (amount, str(v["ccy"])) if amount > 0 else None
    except Exception:
        return None


def email_enabled():
    v = load_pref(PREF_KEY)
    return bool(isinstance(v, dict) and v.get("email"))


def pace_of(ops, ccy, accounts=None, today=None):
    """(start, depuneri nete, luni, ritm lunar) in moneda ccy, pentru conturile date (toate daca None);
    lunile se numara de cand depunerile nete trec de 50 EUR (fara sumele de proba de la inceput)."""
    import journal
    from portfolio_model import fx
    net = sum(amount * float(fx(c, ccy) or 0) for c, amount in journal.net_deposits(ops, accounts).items())
    start = (journal.start_above(ops, PACE_MIN_EUR, lambda c: fx(c, "EUR"), accounts)
             or journal.first_investment(ops, accounts))
    if not start or net <= 0:
        return start, net, None, None
    months = journal.months_since(start, today)
    return start, net, months, net / months


def check_and_notify(user, ops=None, today=None):
    """Email cand ritmul lunar (toate conturile) scade sub tinta; o singura data pana revine la tinta.
    Intoarce True daca a trimis."""
    tg = load()
    state = load_json_file(STATE_FILE, {})
    if not tg or not email_enabled():
        if state.get("below"):
            save_json_file(STATE_FILE, {"below": False})
        return False
    if ops is None:
        import journal
        ops = journal.load_all({})
    _, _, months, pace = pace_of(ops, tg[1], None, today)
    if pace is None:
        return False
    if pace >= tg[0]:
        if state.get("below"):
            save_json_file(STATE_FILE, {"below": False})
        return False
    if state.get("below") or pace >= tg[0] * EMAIL_MARGIN:
        return False
    sent = _send(user, pace, tg, months)
    if sent:
        save_json_file(STATE_FILE, {"below": True})
    return sent


def _send(user, pace, tg, months):
    import notify
    import users
    from events import _user_lang
    email = users.email(user) if user else None
    if not email:
        return False
    lang = _user_lang()
    amount, ccy = tg
    missing = (amount - pace) * months  # cat ar trebui depus acum ca ritmul sa ajunga la tinta
    body = t("pace.mail_body", _lang=lang, pace="%.2f %s" % (pace, ccy), target="%.2f %s" % (amount, ccy),
             p="%.0f" % (pace / amount * 100), missing="%.2f %s" % (missing, ccy))
    return notify.notify("pace", t("pace.mail_subject", _lang=lang), body, to=[email], sync=True,
                         key="pace:%s:%s" % (user, int(pace * 100)), min_hours=0)


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
    mail = st.toggle(t("pace.email"), value=email_enabled(), key="pace_target_email", disabled=amount <= 0,
                     help=t("pace.email_help"))
    new = {"amount": float(amount), "ccy": ccy, "email": bool(mail)} if amount > 0 else None
    if new != (load_pref(PREF_KEY) or None):
        save_pref(PREF_KEY, new)
        st.toast(t("pace.saved"))
