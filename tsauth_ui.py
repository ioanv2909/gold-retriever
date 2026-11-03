"""Tailscale in Setari: configurarea si legarea conturilor (admin, Setari -> Utilizatori) si legarea propriului
cont (Setari -> Securitate). Logica e in tsauth.py, conturile in users.py."""
import streamlit as st

import alerts
import tsauth
import users
from i18n import t


def _here():
    login, name = tsauth.identity()
    if login:
        st.caption(t("ts.here", login=login, name=name or login))
    elif tsauth.via_tailscale():
        st.caption(t("ts.here_tagged"))
    else:
        st.caption(t("ts.here_none"))


def _rotate(me):
    """Callback: secretul nou, bifa de confirmare stearsa (inainte ca widget-urile sa fie desenate din nou)."""
    tsauth.rotate_secret()
    alerts.record_user_event("secret Tailscale regenerat", me, me, "")
    st.session_state["ts_rot_sure"] = False
    st.session_state["_ts_rotated"] = True


def render_admin(me):
    """Admin: comanda `tailscale serve`, adresa, legarea fiecarui cont de un login Tailscale."""
    st.markdown("#### " + t("ts.title"))
    st.caption(t("ts.intro", port=tsauth.HTTPS_PORT))
    st.markdown(t("ts.setup"))
    cmd = tsauth.serve_command()
    st.code(cmd, language="bash")
    import appearance
    appearance.copy_button(cmd, "ts_cmd", t("ts.copy"), t("ts.copied"))
    st.caption(t("ts.setup_note"))
    _here()
    with st.expander(t("ts.rotate_title")):
        st.caption(t("ts.rotate_help", port=tsauth.HTTPS_PORT))
        if st.session_state.pop("_ts_rotated", False):
            st.success(t("ts.rotated"))
        sure = st.checkbox(t("ts.rotate_confirm"), key="ts_rot_sure")
        st.button(t("ts.rotate"), key="ts_rot", disabled=not sure, on_click=_rotate, args=(me,))

    st.markdown("**" + t("ts.links") + "**")
    recs = users.records()
    st.dataframe([{t("ts.col_user"): r["name"], t("ts.col_login"): r.get("ts_login") or "—"} for r in recs],
                 hide_index=True, width="content")
    c1, c2, c3 = st.columns([2, 3, 2], vertical_alignment="bottom")
    who = c1.selectbox(t("ts.col_user"), [r["key"] for r in recs], key="ts_adm_user",
                       format_func=lambda k: next((r["name"] for r in recs if r["key"] == k), k))
    login = c2.text_input(t("ts.col_login"), value=users.ts_login(who) or "", key="ts_adm_login_" + str(who),
                          placeholder="nume@gmail.com", help=t("ts.login_help"))
    if c3.button(t("ts.save"), key="ts_adm_save"):
        err = users.set_ts_login(who, login)
        if err:
            st.error(t("ts.err_" + err))
        else:
            alerts.record_user_event("cont Tailscale legat" if login.strip() else "cont Tailscale dezlegat", me, who,
                                     "login: " + login.strip() if login.strip() else "")
            st.success(t("ts.saved"))


def render_own(me):
    """Utilizatorul: leaga sau dezleaga propriul cont de login-ul Tailscale al cererii curente."""
    st.markdown("#### " + t("ts.title"))
    mine = users.ts_login(me)
    login, _ = tsauth.identity()
    if mine:
        st.caption(t("ts.linked", login=mine))
    else:
        st.caption(t("ts.unlinked"))
    _here()
    c1, c2 = st.columns(2)
    if login and login != mine and c1.button(t("ts.link_me", login=login), key="ts_own_link"):
        err = users.set_ts_login(me, login)
        if err:
            st.error(t("ts.err_" + err))
        else:
            alerts.record_user_event("cont Tailscale legat", me, me, "login: " + login)
            st.success(t("ts.saved"))
            st.rerun()
    if mine and c2.button(t("ts.unlink_me"), key="ts_own_unlink"):
        users.set_ts_login(me, "")
        alerts.record_user_event("cont Tailscale dezlegat", me, me, "")
        st.success(t("ts.saved"))
        st.rerun()
