"""Setari -> Utilizatori -> Conectati acum (doar admin)."""
import time

import streamlit as st

import alerts
import presence
import users
from i18n import t


def _ago(sec):
    m = int(max(0, sec) // 60)
    return t("pres.just_now") if m < 1 else t("pres.ago", m=m)


def rows(me, now=None):
    """Randurile tabelului; None pentru un utilizator care nu e admin."""
    if users.role(me) != "admin":
        return None
    now = now if now is not None else time.time()
    out = []
    for r in presence.online(now):
        if not users.exists(r["user"]):
            continue  # cont sters intre timp
        out.append({
            t("pres.col.user"): r["user"],
            t("pres.col.role"): users.role(r["user"]),
            t("pres.col.last"): _ago(now - r["last"]),
            t("pres.col.first"): time.strftime("%Y-%m-%d %H:%M", time.localtime(r["first"])),
            t("pres.col.device"): presence.device(r["ua"]),
            t("pres.col.ip"): r["ip"] or "—",
            t("pres.col.sessions"): r["sessions"],
        })
    return out


def render_online(me):
    data = rows(me)
    if data is None:
        return
    import pandas as pd
    if st.button(t("pres.refresh"), key="pres_refresh"):
        st.rerun()
    fl = st.session_state.pop("_pres_flash", None)
    if fl:
        (st.success if fl[0] == "ok" else st.error)(fl[1])
    st.caption(t("pres.caption", n=len(data), m=presence.ONLINE_WINDOW // 60))
    if not data:
        st.info(t("pres.none"))
        return
    st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")

    others = [r[t("pres.col.user")] for r in data if r[t("pres.col.user")] != str(me).lower()]
    if not others:
        return
    st.markdown("**" + t("pres.kick") + "**")
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    who = c1.selectbox(t("pres.col.user"), others, key="pres_kick_user")
    if c2.button(t("pres.kick"), key="pres_kick"):
        if users.bump_session(who) is None:
            presence.forget_user(who)
            try:
                alerts.record_user_event("deconectare fortata", me, who)
            except Exception:
                pass
            st.session_state["_pres_flash"] = ("ok", t("pres.kicked", u=who))
        else:
            st.session_state["_pres_flash"] = ("err", t("pres.kick_err"))
        st.rerun()
