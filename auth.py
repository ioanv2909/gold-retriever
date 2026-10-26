import ipaddress
import os
import re
import secrets
import time

import alerts
import streamlit as st

from appearance import _run_js
from url_tabs import reset as reset_tabs

import known_devices
import presence
import session_policy
import users

_COOKIE = "pt_auth"
_MAX_FAILS = 5
_LOCK_SECONDS = 300
_FAIL_DELAY = 1
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
    # st.html cu JavaScript ruleaza direct in pagina (fara iframe); inlocuieste components.html
    _run_js("document.cookie = '%s=%s; max-age=%d; path=/; SameSite=Lax';" % (_COOKIE, value, max_age))


def _read_cookie():
    try:
        return st.context.cookies.get(_COOKIE)
    except Exception:
        return None


def _set_session(key):
    st.session_state["_user"] = key
    st.session_state["_sess_ver"] = users.session_version(key)
    st.session_state.pop("_auth_loggedout", None)


def _start_cookie_session(tok, fresh):
    """Leaga sesiunea de cookie: limita absoluta din token, activitatea de acum."""
    now = time.time()
    tid = session_policy.token_id(tok)
    st.session_state["_tok_id"] = tid
    st.session_state["_auth_exp"] = users.token_exp(tok)
    st.session_state["_last_active"] = now
    session_policy.touch(tid, now, force=fresh or session_policy.last_activity(tid) is None)
    _check_device(st.session_state.get("_user"))


def _client():
    """(User-Agent, IP) ale cererii curente; IP-ul din X-Forwarded-For e doar informativ."""
    h = st.context.headers
    fwd = (h.get("X-Forwarded-For") or "").split(",")[0].strip()
    return h.get("User-Agent"), fwd or st.context.ip_address


def _log(event, user=None, **kw):
    """O linie in logul containerului pentru autentificare (Setari -> Log). Fara parole sau token-uri;
    un nume care nu arata a nume de cont (poate o parola scrisa in campul gresit) apare ca <invalid>."""
    try:
        ip = _client()[1]
    except Exception:
        ip = None
    name = str(user).strip().lower() if user else "-"
    if name != "-" and not re.fullmatch(r"[a-z0-9_-]{1,32}", name):
        name = "<invalid>"
    try:
        ip = str(ipaddress.ip_address(str(ip).strip())) if ip else "-"
    except ValueError:
        ip = "<invalid>"  # X-Forwarded-For vine de la client
    extra = "".join(" %s=%s" % kv for kv in kw.items())
    print("[auth] %s user=%s ip=%s%s" % (event, name, ip, extra), flush=True)


def _check_device(me):
    """O data pe sesiune, la autentificare (parola sau cookie): alerta daca dispozitivul e nou pentru cont."""
    if not me or st.session_state.get("_device_checked") == me:
        return
    st.session_state["_device_checked"] = me
    try:
        ua, ip = _client()
        known_devices.check_login(me, ua, ip)
    except Exception:
        pass


def _issue_cookie(key):
    tok = users.make_token(key)
    _cookie_js(tok, session_policy.max_seconds())
    _start_cookie_session(tok, True)


def _mark_activity():
    """O rulare ceruta de utilizator (nu heartbeat-ul sau o reincarcare automata)."""
    if st.session_state.pop("_auto_rerun", False):
        return
    now = time.time()
    st.session_state["_last_active"] = now
    session_policy.touch(st.session_state.get("_tok_id"), now)


def auto_rerun():
    """st.rerun() pornit de cod (fragmente periodice): nu conteaza ca activitate."""
    st.session_state["_auto_rerun"] = True
    st.rerun()



# contor de esecuri pe cont, comun pentru login si schimbarea parolei
def _lock_remaining(key):
    """Secunde ramase din blocare (0 daca nu e blocat)."""
    return max(0.0, _fails.get(key, (0, 0.0))[1] - time.time())


def _register_fail(key):
    cnt, until = _fails.get(key, (0, 0.0))
    cnt += 1
    if cnt >= _MAX_FAILS:
        _log("account locked", key, failures=_MAX_FAILS, seconds=_LOCK_SECONDS)
        try:
            alerts.record_lockout(key, users.exists(key), _MAX_FAILS, _LOCK_SECONDS)
        except Exception:
            pass
        cnt, until = 0, time.time() + _LOCK_SECONDS
    _fails[key] = (cnt, until)
    time.sleep(_FAIL_DELAY)


def _clear_fails(key):
    _fails.pop(key, None)


def change_own_password(me, current, new, confirm):
    """Schimbarea propriei parole; me vine din sesiunea autentificata, niciodata din formular.
    Returneaza None sau cod_eroare ("locked", "mismatch", "bad_current", "pwd_short")."""
    key = str(me).strip().lower()
    if _lock_remaining(key):
        return "locked"
    if new != confirm:
        return "mismatch"
    err = users.change_password(key, current, new)
    if err == "bad_current":
        _log("password change failed", key, reason="bad current password")
        _register_fail(key)
    if err:
        return err
    _clear_fails(key)
    _log("password changed", key)
    try:
        alerts.record_user_event("parola schimbata de utilizator", key, key)
    except Exception:
        pass
    return None


def render_change_password(me):
    """Formularul „Schimba parola”. Returneaza True dupa o schimbare reusita."""
    from i18n import t
    with st.form("pwd_change_form", clear_on_submit=True):
        cur = st.text_input(t("pwd.current"), type="password")
        new = st.text_input(t("pwd.new"), type="password")
        new2 = st.text_input(t("pwd.confirm"), type="password")
        go = st.form_submit_button(t("pwd.submit"))
    if not go:
        return False
    err = change_own_password(me, cur, new, new2)
    if err == "locked":
        st.error(t("pwd.err_locked", m=int(_lock_remaining(str(me).lower()) // 60) + 1))
    elif err:
        st.error(t("pwd.err_" + err))
    else:
        # semnatura token-ului include hash-ul parolei: celelalte sesiuni ies, aceasta primeste cookie nou
        _issue_cookie(me)
        st.success(t("pwd.ok"))
        return True
    return False


def _logout():
    _log("logout", st.session_state.get("_user"))
    try:
        presence.forget_session(st.session_state.pop("_presence_id", None))
    except Exception:
        pass
    try:
        session_policy.revoke(st.session_state.get("_tok_id"))
    except Exception:
        pass
    for k in ("_tok_id", "_auth_exp", "_last_active", "_device_checked"):
        st.session_state.pop(k, None)
    st.session_state.pop("_user", None)
    st.session_state.pop("_page", None)
    st.query_params.pop("page", None)
    reset_tabs("settings_tab")
    st.session_state["_auth_loggedout"] = True
    st.session_state["_auth_clear_cookie"] = True
    st.rerun()


def _forced_change(me):
    """Parola data de admin trebuie schimbata inainte de a folosi aplicatia."""
    from i18n import t
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        st.markdown("### " + t("pwd.title"))
        st.warning(t("pwd.forced"))
        if render_change_password(me):
            st.button(t("pwd.continue"), key="pwd_forced_continue")
        elif st.button(_tr("logout"), key="pwd_forced_logout"):
            _logout()
    st.stop()


def require_login():
    """Returneaza cheia utilizatorului autentificat; opreste scriptul daca nu e logat."""
    key = _authenticate()
    _heartbeat()
    if users.must_change(key):
        _forced_change(key)
    return key


def _session_expired(now=None):
    """Limita absoluta a cookie-ului depasita sau inactivitate peste limita (session_policy)."""
    exp = st.session_state.get("_auth_exp")
    return (exp is not None and session_policy.token_expired(exp, now)) or \
        session_policy.is_idle(st.session_state.get("_last_active"), now)


def _session_valid(me):
    """Sesiunea deschisa e valida cat timp contul exista, nu a fost deconectat fortat de un admin si nu a expirat."""
    return bool(me) and users.exists(me) and users.session_version(me) == st.session_state.get("_sess_ver", 0) \
        and not _session_expired()


def _track(me):
    sid = st.session_state.get("_presence_id")
    if not sid:
        sid = st.session_state["_presence_id"] = secrets.token_hex(8)
    try:
        # in spatele unui reverse proxy ip_address e adresa proxy-ului; antetul e doar informativ
        presence.touch(sid, me, *_client())
    except Exception:
        pass


@st.fragment(run_every=60)
def _heartbeat():
    """Cat timp tabul e deschis: tine prezenta la zi si scoate in cel mult un minut o sesiune deconectata fortat."""
    me = st.session_state.get("_user")
    if not _session_valid(me):
        auto_rerun()
    _track(me)


def _authenticate():
    me = st.session_state.get("_user")
    if _session_valid(me):
        _mark_activity()
        _chrome(me)
        return me
    st.session_state.pop("_auto_rerun", None)
    if me and users.exists(me):
        st.session_state["_auth_clear_cookie"] = True  # deconectare fortata sau expirare: cookie-ul vechi nu mai e valid
        if _session_expired():
            st.session_state["_auth_expired"] = True
            _log("session ended", me, reason="expired")
        else:
            _log("session ended", me, reason="signed out by admin")
    elif me:
        _log("session ended", me, reason="account deleted")
    for k in ("_user", "_tok_id", "_auth_exp", "_last_active"):
        st.session_state.pop(k, None)

    if not st.session_state.get("_auth_loggedout") and not st.session_state.get("_auth_clear_cookie"):
        tok = _read_cookie()
        who = users.check_token(tok) if tok else None
        if who and session_policy.is_idle(session_policy.last_activity(session_policy.token_id(tok))):
            _log("cookie rejected", who, reason="idle")
            who = None
            st.session_state["_auth_expired"] = True
            st.session_state["_auth_clear_cookie"] = True
        elif tok and not who and users.token_exp(tok) is not None and users.token_exp(tok) < time.time():
            _log("cookie rejected", reason="expired")
            st.session_state["_auth_expired"] = True
            st.session_state["_auth_clear_cookie"] = True
        elif tok and not who:
            _log("cookie rejected", reason="invalid")
        if who:
            _log("session resumed", who, via="cookie")
            _set_session(who)
            _start_cookie_session(tok, False)
            _chrome(who)
            return who

    if st.session_state.pop("_auth_clear_cookie", False):
        _cookie_js("", 0)

    setup = not users.has_users()
    ph = st.empty()
    with ph.container():
        _, mid, _ = st.columns([1, 1, 1])
        with mid:
            # sigla si numele aplicatiei (scurt, ca sa incapa pe telefon), apoi titlul formularului
            logo = ""
            if os.path.exists("assets/icon-192.png"):
                import base64
                with open("assets/icon-192.png", "rb") as f:
                    logo = '<img src="data:image/png;base64,%s" width="64">' % base64.b64encode(f.read()).decode()
            st.markdown(
                '<div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.5rem">%s'
                '<span style="font-size:1.6rem;font-weight:700;line-height:1.2">GoldRetriever</span></div>' % logo,
                unsafe_allow_html=True,
            )
            st.markdown("### " + _tr("title_setup" if setup else "title_login"))
            if st.session_state.get("_auth_expired"):
                import i18n
                st.warning(i18n.t("sess.expired"))
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
        _log("admin created", key)
    else:
        left = _lock_remaining(key)
        if left:
            _log("login refused", key, reason="locked", seconds_left=int(left))
            with mid:
                st.error(_tr("locked", m=int(left // 60) + 1))
            st.stop()
        if not users.verify(key, pw):
            _log("login failed", key, reason="bad user or password")
            _register_fail(key)
            with mid:
                st.error(_tr("bad"))
            st.stop()
        _clear_fails(key)
        _log("login ok", key, via="password")

    _set_session(key)
    st.session_state.pop("_auth_expired", None)
    ph.empty()
    _issue_cookie(key)
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
    from i18n import t
    t_list, t_add, t_manage, t_online, t_sess = st.tabs(
        [_tr("tab_list"), _tr("tab_add"), _tr("tab_manage"), t("pres.tab"), t("sess.tab")])

    with t_online:
        from presence_ui import render_online
        render_online(me)

    with t_sess:
        from session_policy_ui import render_session_policy
        render_session_policy(me)

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
                _, err = users.create_user(n_name, n_pwd, n_role, must_change=True)
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
                # parola data de admin se schimba la urmatoarea autentificare (nu si pentru propriul cont)
                err = users.set_password(r_user, r_pwd, must_change=r_user != me)
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
            "div[data-testid='stPopoverBody']:has(.um-marker){width:13rem !important;min-width:0 !important;}"
            "</style>",
            unsafe_allow_html=True,
        )
        st.caption(users.role(me))
        import mobile
        from i18n import t
        _compact = mobile.compact()
        if _btn(t("mob.full") if _compact else t("mob.compact"), "menu_view"):
            mobile.set_mode("full" if _compact else "compact")
            st.rerun()
        if _btn(t("app.print"), "menu_print"):
            import appearance
            appearance.print_page()
        if _btn("⚙️ " + _tr("settings"), "menu_settings"):
            # URL-ul dedicat pastreaza pagina la refresh; pagina pozitiei se inchide
            for k in ("selected_ticker", "selected_row", "_url_ticker"):
                st.session_state.pop(k, None)
            st.query_params.pop("detail", None)
            reset_tabs("settings_tab")
            st.query_params["page"] = "settings"
            st.session_state["_page"] = "settings"
            st.rerun()
        if _btn(_tr("logout"), "menu_logout"):
            _logout()
