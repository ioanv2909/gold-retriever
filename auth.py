import time

import alerts
import streamlit as st
import streamlit.components.v1 as components

import users

_COOKIE = "pt_auth"
_DAYS = 30
_MAX_FAILS = 5
_LOCK_SECONDS = 300
_fails = {}

_S = {
    "title_login": ("🔒 Autentificare", "🔒 Sign in"),
    "title_setup": ("👋 Configurare inițială", "👋 First-time setup"),
    "setup_info": ("Creează contul de administrator. Datele existente vor fi atribuite acestui cont.",
                   "Create the administrator account. Existing data will be assigned to this account."),
    "user": ("Utilizator", "Username"),
    "pwd": ("Parola", "Password"),
    "pwd2": ("Confirmă parola", "Confirm password"),
    "btn_login": ("Intră", "Sign in"),
    "btn_create": ("Creează contul", "Create account"),
    "bad": ("Utilizator sau parolă incorecte.", "Wrong username or password."),
    "locked": ("Prea multe încercări. Reîncearcă în {m} min.", "Too many attempts. Try again in {m} min."),
    "mismatch": ("Parolele nu coincid.", "Passwords do not match."),
    "logout": ("🔓 Deconectare", "🔓 Log out"),
    "admin_title": ("👥 Utilizatori", "👥 Users"),
    "new_user": ("Utilizator nou", "New user"),
    "role": ("Rol", "Role"),
    "add": ("Adaugă", "Add"),
    "reset": ("Resetează parola", "Reset password"),
    "new_pwd": ("Parolă nouă", "New password"),
    "apply": ("Aplică", "Apply"),
    "delete": ("Șterge utilizator", "Delete user"),
    "purge": ("Șterge și datele lui", "Also delete their data"),
    "ok_created": ("Utilizator creat.", "User created."),
    "ok_pwd": ("Parola a fost schimbată.", "Password changed."),
    "ok_deleted": ("Utilizator șters.", "User deleted."),
    "err_name": ("Nume invalid (2–32 caractere: litere, cifre, _ sau -).", "Invalid name (2–32 chars: letters, digits, _ or -)."),
    "err_pwd_short": ("Parola trebuie să aibă minim 8 caractere.", "Password must be at least 8 characters."),
    "err_exists": ("Utilizatorul există deja.", "User already exists."),
    "err_last_admin": ("Nu poți șterge ultimul administrator.", "You cannot delete the last administrator."),
    "err_self": ("Nu te poți șterge pe tine.", "You cannot delete yourself."),
}


def _tr(key, **kw):
    try:
        from i18n import lang
        i = 1 if lang() == "EN" else 0
    except Exception:
        i = 0
    return _S[key][i].format(**kw)


def _cookie_js(value, max_age):
    js = (
        "<script>var c='%s=%s; max-age=%d; path=/; SameSite=Lax';"
        "try{window.parent.document.cookie=c;}catch(e){document.cookie=c;}</script>"
    ) % (_COOKIE, value, max_age)
    components.html(js, height=0)


def _read_cookie():
    try:
        return st.context.cookies.get(_COOKIE)
    except Exception:
        return None


def _set_session(key):
    st.session_state["_user"] = key
    st.session_state.pop("_auth_loggedout", None)


def require_login():
    """Returneaza cheia utilizatorului autentificat; opreste scriptul daca nu e logat."""
    me = st.session_state.get("_user")
    if me and users.exists(me):
        _chrome(me)
        return me
    st.session_state.pop("_user", None)

    if not st.session_state.get("_auth_loggedout"):
        tok = _read_cookie()
        who = users.check_token(tok) if tok else None
        if who:
            _set_session(who)
            _chrome(who)
            return who

    if st.session_state.pop("_auth_clear_cookie", False):
        _cookie_js("", 0)

    setup = not users.has_users()
    ph = st.empty()
    with ph.container():
        _, mid, _ = st.columns([1, 1, 1])
        with mid:
            st.markdown("### " + _tr("title_setup" if setup else "title_login"))
            if setup:
                st.info(_tr("setup_info"))
            with st.form("login_form"):
                uname = st.text_input(_tr("user"))
                pw = st.text_input(_tr("pwd"), type="password")
                pw2 = st.text_input(_tr("pwd2"), type="password") if setup else None
                go = st.form_submit_button(_tr("btn_create" if setup else "btn_login"))
    if not go:
        st.stop()

    key = uname.strip().lower()

    if setup:
        if pw != pw2:
            with mid:
                st.error(_tr("mismatch"))
            st.stop()
        new_key, err = users.create_user(uname, pw, "admin")
        if err:
            with mid:
                st.error(_tr("err_" + err))
            st.stop()
        users.migrate_legacy(new_key)
        key = new_key
    else:
        cnt, until = _fails.get(key, (0, 0.0))
        now = time.time()
        if now < until:
            with mid:
                st.error(_tr("locked", m=int((until - now) // 60) + 1))
            st.stop()
        if not users.verify(key, pw):
            cnt += 1
            if cnt >= _MAX_FAILS:
                try:
                    alerts.record_lockout(key, users.exists(key), _MAX_FAILS, _LOCK_SECONDS)
                except Exception:
                    pass
                cnt, until = 0, now + _LOCK_SECONDS
            _fails[key] = (cnt, until)
            time.sleep(1)
            with mid:
                st.error(_tr("bad"))
            st.stop()
        _fails.pop(key, None)

    _set_session(key)
    ph.empty()
    _cookie_js(users.make_token(key, _DAYS), _DAYS * 86400)
    _chrome(key)
    return key


def _chrome(me):
    return  # replaced by user_menu() in the page header


_S.update({
    "back": ("← Înapoi la aplicație", "← Back to app"),
    "tab_list": ("Listă", "List"),
    "tab_add": ("Adaugă", "Add"),
    "tab_manage": ("Gestionare", "Manage"),
    "col_user": ("Utilizator", "Username"),
    "col_role": ("Rol", "Role"),
    "col_created": ("Creat", "Created"),
    "set_role": ("Schimbă rolul", "Change role"),
    "ok_role": ("Rol schimbat.", "Role changed."),
})


def _flash(kind, text):
    st.session_state["_adm_flash"] = (kind, text)
    st.rerun()


def render_users_page(me, embedded=False):
    import pandas as pd

    if users.role(me) != "admin":
        st.session_state.pop("_page_users", None)
        st.rerun()

    if not embedded:
        top = st.columns([1, 4])
        if top[0].button(_tr("back"), key="users_back"):
            st.session_state.pop("_page_users", None)
            st.rerun()
        top[1].markdown("## " + _tr("admin_title"))

    fl = st.session_state.pop("_adm_flash", None)
    if fl:
        (st.success if fl[0] == "ok" else st.error)(fl[1])

    names = users.names()
    t_list, t_add, t_manage = st.tabs([_tr("tab_list"), _tr("tab_add"), _tr("tab_manage")])

    with t_list:
        rows = [
            {
                _tr("col_user"): r["name"],
                _tr("col_role"): r["role"],
                _tr("col_created"): time.strftime("%Y-%m-%d", time.localtime(r["created"])) if r.get("created") else "",
            }
            for r in users.records()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with t_add:
        with st.form("adm_add_form", clear_on_submit=True):
            n_name = st.text_input(_tr("user"))
            n_pwd = st.text_input(_tr("pwd"), type="password")
            n_role = st.selectbox(_tr("role"), ["user", "admin"])
            if st.form_submit_button(_tr("add")):
                _, err = users.create_user(n_name, n_pwd, n_role)
                if not err:
                    alerts.record_user_event("utilizator creat", me, n_name, "rol: " + str(n_role))
                _flash("err", _tr("err_" + err)) if err else _flash("ok", _tr("ok_created"))

    with t_manage:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**" + _tr("reset") + "**")
            r_user = st.selectbox(_tr("user"), names, key="adm_rst_user")
            r_pwd = st.text_input(_tr("new_pwd"), type="password", key="adm_rst_pwd")
            if st.button(_tr("apply"), key="adm_rst"):
                err = users.set_password(r_user, r_pwd)
                if not err:
                    alerts.record_user_event("parola resetata", me, r_user)
                _flash("err", _tr("err_" + err)) if err else _flash("ok", _tr("ok_pwd"))
        with c2:
            st.markdown("**" + _tr("set_role") + "**")
            s_user = st.selectbox(_tr("user"), names, key="adm_role_user")
            s_role = st.selectbox(_tr("role"), ["user", "admin"], key="adm_role_val")
            if st.button(_tr("apply"), key="adm_role"):
                err = users.set_role(s_user, s_role)
                if not err:
                    alerts.record_user_event("rol schimbat", me, s_user, "rol nou: " + str(s_role))
                _flash("err", _tr("err_" + err)) if err else _flash("ok", _tr("ok_role"))
        with c3:
            st.markdown("**" + _tr("delete") + "**")
            d_user = st.selectbox(_tr("user"), names, key="adm_del_user")
            d_purge = st.checkbox(_tr("purge"), key="adm_del_purge")
            if st.button(_tr("delete"), key="adm_del"):
                err = users.delete_user(d_user, me, d_purge)
                if not err:
                    alerts.record_user_event("utilizator sters", me, d_user, "date sterse" if d_purge else "date pastrate")
                _flash("err", _tr("err_" + err)) if err else _flash("ok", _tr("ok_deleted"))


_S.update({
    "settings": ("Setări", "Settings"),
})


def _btn(label, key):
    try:
        return st.button(label, key=key, width="stretch")
    except TypeError:
        return st.button(label, key=key, use_container_width=True)


def user_menu(me):
    """Top-right user menu: Settings / Log out."""
    try:
        pop = st.popover("👤 " + me)
    except TypeError:
        pop = st.popover("👤 " + me)
    with pop:
        st.markdown(
            "<span class='um-marker'></span><style>"
            "div[data-testid='stPopoverBody']:has(.um-marker){width:11rem !important;min-width:0 !important;}"
            "</style>",
            unsafe_allow_html=True,
        )
        st.caption(users.role(me))
        if _btn("⚙️ " + _tr("settings"), "menu_settings"):
            # URL-ul dedicat pastreaza pagina la refresh; pagina pozitiei se inchide
            for k in ("selected_ticker", "selected_row", "_url_ticker"):
                st.session_state.pop(k, None)
            st.query_params.pop("detail", None)
            st.query_params.pop("tab", None)
            st.session_state.pop("settings_tab", None)
            st.query_params["page"] = "settings"
            st.session_state["_page"] = "settings"
            st.rerun()
        if _btn(_tr("logout"), "menu_logout"):
            st.session_state.pop("_user", None)
            st.session_state.pop("_page", None)
            st.query_params.pop("page", None)
            st.query_params.pop("tab", None)
            st.session_state["_auth_loggedout"] = True
            st.session_state["_auth_clear_cookie"] = True
            st.rerun()
