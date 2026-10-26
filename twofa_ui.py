"""Setari -> Securitate: activarea / dezactivarea 2FA si codurile de rezerva; politica 2FA (admin)."""
import streamlit as st

import alerts
import twofa
import users
from i18n import t


def _event(action, actor, target, detail=""):
    try:
        alerts.record_user_event(action, actor, target, detail)
    except Exception:
        pass


def _after_change(me):
    """enable/disable cresc sess_ver: sesiunea aceasta ramane deschisa, cu un cookie nou; celelalte ies."""
    import auth
    st.session_state["_sess_ver"] = users.session_version(me)
    auth._issue_cookie(me)


def _show_codes(me):
    codes = st.session_state.get("_tfa_codes")
    if not codes:
        return False
    st.success(t("tfa.codes_title"))
    st.caption(t("tfa.codes_help"))
    text = "\n".join(codes)
    st.code(text, language=None)
    st.download_button(t("tfa.codes_download"), text + "\n", file_name="goldretriever-recovery-codes.txt",
                       mime="text/plain", key="tfa_codes_dl")
    if st.button(t("tfa.codes_saved"), key="tfa_codes_ok"):
        st.session_state.pop("_tfa_codes", None)
        st.rerun()
    return True


def render_enroll(me):
    """Codul QR, cheia si confirmarea cu un cod. Intoarce True dupa activare (codurile sunt afisate)."""
    import auth
    if _show_codes(me):
        return True
    secret = st.session_state.get("_tfa_secret")
    if not secret:
        if st.button(t("tfa.start"), key="tfa_start"):
            st.session_state["_tfa_secret"] = twofa.new_secret()
            st.rerun()
        return False
    st.markdown(t("tfa.scan"))
    st.image(twofa.qr_png(twofa.provisioning_uri(secret, me)), width=220)
    st.caption(t("tfa.manual"))
    st.code(" ".join(secret[i:i + 4] for i in range(0, len(secret), 4)), language=None)
    with st.form("tfa_enroll_form", clear_on_submit=True):
        code = st.text_input(t("tfa.code"), autocomplete="one-time-code", max_chars=10)
        go = st.form_submit_button(t("tfa.enable"))
    if st.button(t("tfa.cancel"), key="tfa_cancel"):
        st.session_state.pop("_tfa_secret", None)
        st.rerun()
    if not go:
        return False
    codes, err = users.enable_2fa(me, secret, code)
    if err:
        st.error(t("tfa.bad_code"))
        return False
    st.session_state.pop("_tfa_secret", None)
    st.session_state["_tfa_codes"] = codes
    _after_change(me)
    auth._log("2fa enabled", me)
    _event("2FA activat", me, me)
    st.rerun()


def _confirm_form(me, key, label):
    """Parola + un cod (TOTP sau de rezerva), cu aceeasi blocare ca la autentificare. True daca sunt corecte."""
    import auth
    with st.form(key, clear_on_submit=True):
        pw = st.text_input(t("pwd.current"), type="password")
        code = st.text_input(t("tfa.code_or_recovery"), autocomplete="one-time-code", max_chars=20)
        go = st.form_submit_button(label)
    if not go:
        return False
    me_key = str(me).lower()
    left = auth._lock_remaining(me_key)
    if left:
        st.error(t("pwd.err_locked", m=int(left // 60) + 1))
        return False
    if not users.verify(me_key, pw) or not users.verify_2fa(me_key, code):
        auth._log("2fa change failed", me_key, reason="bad password or code")
        auth._register_fail(me_key)
        st.error(t("tfa.bad_confirm"))
        return False
    auth._clear_fails(me_key)
    return True


def render_security(me):
    import auth
    st.markdown("#### " + t("tfa.title"))
    st.caption(t("tfa.help"))
    if not users.has_2fa(me):
        if twofa.required(me, users.role(me)):
            st.warning(t("tfa.forced"))
        render_enroll(me)
        return
    if _show_codes(me):
        return
    st.success(t("tfa.on", n=users.recovery_left(me)))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**" + t("tfa.new_codes") + "**")
        if _confirm_form(me, "tfa_codes_form", t("tfa.new_codes")):
            st.session_state["_tfa_codes"] = users.new_recovery_codes(me)
            auth._log("2fa recovery codes regenerated", me)
            _event("coduri de rezerva 2FA noi", me, me)
            st.rerun()
    with c2:
        st.markdown("**" + t("tfa.disable") + "**")
        if twofa.required(me, users.role(me)):
            st.caption(t("tfa.disable_blocked"))
        elif _confirm_form(me, "tfa_disable_form", t("tfa.disable")):
            users.disable_2fa(me)
            _after_change(me)
            auth._log("2fa disabled", me)
            _event("2FA dezactivat", me, me)
            st.rerun()


def render_admin_reset(me, names):
    """Utilizatori -> Administrare: scoate 2FA unui cont care si-a pierdut telefonul."""
    import auth
    st.markdown("**" + t("tfa.reset") + "**")
    with_2fa = [n for n in names if users.has_2fa(n)]
    if not with_2fa:
        st.caption(t("tfa.reset_none"))
        return
    target = st.selectbox(t("tfa.user"), with_2fa, key="adm_tfa_user")
    if st.button(t("tfa.reset"), key="adm_tfa_reset"):
        users.disable_2fa(target)
        if target == me:
            _after_change(me)
        auth._log("2fa reset", target, by=me)
        _event("2FA resetat", me, target)
        st.session_state["_adm_flash"] = ("ok", t("tfa.reset_ok", u=target))
        st.rerun()


def render_policy(me):
    """Utilizatori -> Sesiuni: cine trebuie sa aiba 2FA."""
    import auth
    st.markdown("#### " + t("tfa.policy"))
    cur = twofa.policy()
    with st.form("tfa_policy_form"):
        new = st.radio(t("tfa.policy"), twofa.POLICIES, index=twofa.POLICIES.index(cur),
                       format_func=lambda p: t("tfa.policy_" + p), label_visibility="collapsed")
        go = st.form_submit_button(t("sess.save"))
    if not go or new == cur:
        return
    twofa.save_policy(new)
    auth._log("2fa policy changed", me, policy=new)
    _event("politica 2FA schimbata", me, "toti utilizatorii", "%s -> %s" % (cur, new))
    st.success(t("tfa.policy_saved"))
