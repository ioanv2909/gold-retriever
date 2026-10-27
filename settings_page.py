"""Settings page: Trading 212 keys, user management (admin), about + release notes."""
import json
import os

import streamlit as st

import users
from i18n import lang_button, t
from url_tabs import reset as reset_tabs, url_tabs
from core import CONFIG_FILE, load_config, save_config

VERSION = "0.2.0"
REPO_URL = "https://github.com/ioanv2909/gold-retriever"


def _L(ro, en):
    return ro if str(st.session_state.get("lang", "")).upper().startswith("RO") else en


def _tab_t212():
    cfg = load_config()
    st.caption(_L(
        "Cheile se salvează pe disc, doar pentru contul tău. Creează cheia în Trading 212 cu permisiuni doar de citire.",
        "Keys are saved on disk, for your account only. Create the key in Trading 212 with read-only permissions.",
    ))
    kid = st.text_input(_L("ID-ul cheii API", "API key ID"), value=cfg.get("api_key_id", ""), key="set_kid")
    sec = st.text_input(_L("Cheia secretă", "API secret"), type="password", value=cfg.get("api_secret", ""), key="set_sec")
    mins = st.number_input(
        _L("Interval actualizare automată (minute)", "Auto-refresh interval (minutes)"),
        min_value=1, max_value=1440, value=int(cfg.get("interval_minutes", 15)), key="set_mins",
    )
    if st.button("💾 " + _L("Salvează", "Save"), key="set_save"):
        if save_config(kid, sec, mins):
            st.success(_L("Salvat.", "Saved."))
    st.caption(_L("Fișier: ", "File: ") + f"`{os.path.abspath(CONFIG_FILE)}`")


BROKER_TABS = ("t212", "xtb")


def _tab_brokers(xtb_section):
    """Trading 212 si XTB intr-un singur tab, fiecare broker cu sub-tabul lui."""
    labels = {"t212": "🔑 Trading 212", "xtb": t("side.xtb_import")}
    ids = [i for i in BROKER_TABS if i != "xtb" or xtb_section]
    wanted = st.session_state.pop("_broker_tab", None)
    if wanted in ids:
        st.session_state.pop("broker_tabs", None)
    tabs = st.tabs([labels[i] for i in ids], default=labels[wanted] if wanted in ids else None,
                   key="broker_tabs", on_change="rerun")
    for i, tab in zip(ids, tabs):
        if tab.open is False:
            continue  # se randeaza doar sub-tabul deschis
        with tab:
            if i == "t212":
                _tab_t212()
            else:
                xtb_section()


NOTIFY_TABS = ("weekly", "mail")


def _tab_notifications(me, weekly_section):
    """Raportul saptamanal (fiecare utilizator) si emailul/SMTP (doar admin), fiecare cu sub-tabul lui."""
    labels = {"weekly": t("wr.tab"), "mail": t("set.notify_mail")}
    ids = [i for i in NOTIFY_TABS if (i != "weekly" or weekly_section) and (i != "mail" or users.role(me) == "admin")]
    wanted = st.session_state.pop("_notify_tab", None)
    if wanted in ids:
        st.session_state.pop("notify_tabs", None)
    tabs = st.tabs([labels[i] for i in ids], default=labels[wanted] if wanted in ids else None,
                   key="notify_tabs", on_change="rerun")
    for i, tab in zip(ids, tabs):
        if tab.open is False:
            continue  # se randeaza doar sub-tabul deschis
        with tab:
            if i == "weekly":
                weekly_section()
            else:
                from notify_ui import render_notifications
                render_notifications(me)


def _tab_about():
    st.markdown("### GoldRetriever")
    info = {}
    try:
        with open("build_info.json", encoding="utf-8") as f:
            info = json.load(f)
    except Exception:
        pass
    label = "v" + str(info.get("version") or VERSION)
    if info.get("sha"):
        label += " \u00b7 " + info["sha"] + (_L(" (necomis)", " (uncommitted)") if info.get("dirty") else "")
    st.caption(label)
    st.markdown(
        f"[GitHub]({REPO_URL}) · MIT license\n\n"
        + _L("Aplicație self-hosted pentru analiza portofoliilor Trading 212 și XTB. Datele rămân pe serverul tău.",
             "Self-hosted portfolio analyzer for Trading 212 and XTB. Your data stays on your server.")
    )
    st.caption("Logo: dog illustration derived from Noto Emoji (Google), Apache License 2.0.")
    st.markdown("#### " + _L("Note de versiune", "Release notes"))
    try:
        with open("CHANGELOG.md", encoding="utf-8") as f:
            st.markdown(f.read())
    except OSError:
        st.caption(_L("CHANGELOG.md lipsește.", "CHANGELOG.md not found."))


def _tab_password(me):
    from auth import render_change_password
    from twofa_ui import render_security
    st.markdown("#### " + t("pwd.title"))
    render_change_password(me)
    st.divider()
    render_security(me)


def _tab_users(me):
    from auth import render_users_page
    render_users_page(me, embedded=True)


def render_settings(me, sections=()):
    top = st.columns([2, 7, 2], vertical_alignment="center")
    if top[0].button(_L("← Înapoi", "← Back"), key="settings_back"):
        st.session_state.pop("_page", None)
        st.query_params.pop("page", None)
        reset_tabs("settings_tab")
        st.rerun()
    top[1].markdown("## ⚙️ " + _L("Setări", "Settings"))
    with top[2]:
        # aceeasi cheie ca in pagina principala, deci limba se salveaza la fel
        lang_button("lang_switch_settings")

    # (id, eticheta, functie); id-ul apare in URL (?tab=...), deci nu depinde de limba
    sections = list(sections)
    xtb = next((fn for i, _, fn in sections if i == "xtb"), None)
    entries = [("brokers", t("set.brokers"), lambda: _tab_brokers(xtb))]
    entries.append(("password", t("pwd.tab"), lambda: _tab_password(me)))
    weekly = next((fn for i, _, fn in sections if i == "weekly"), None)
    notify_entry = ("notifications", "📬 " + _L("Notificări", "Notifications"), lambda: _tab_notifications(me, weekly))
    # Notificarile stau unde era raportul saptamanal; fara raport (si fara admin) tabul lipseste
    for s in sections:
        if s[0] == "weekly":
            entries.append(notify_entry)
        elif s[0] != "xtb":
            entries.append(s)
    if not weekly and users.role(me) == "admin":
        entries.append(notify_entry)
    if users.role(me) == "admin":
        entries.append(("users", "👥 " + _L("Utilizatori", "Users"), lambda: _tab_users(me)))
    entries.append(("about", "ℹ️ " + _L("Despre", "About"), _tab_about))

    if users.role(me) == "admin":
        from health_ui import render_status
        entries.insert(len(entries) - 1, ("status", t("hs.tab"), lambda: render_status(me)))
        from backup_ui import render_backup
        entries.insert(len(entries) - 1, ("backup", t("bk.tab"), lambda: render_backup(me)))
        from log_ui import render_log
        entries.insert(len(entries) - 1, ("log", t("lg.tab"), lambda: render_log(me)))
    if st.query_params.get("tab") in BROKER_TABS:
        # linkurile vechi ?tab=t212 / ?tab=xtb deschid acum Brokeri, cu sub-tabul lor
        st.session_state["_broker_tab"] = st.query_params["tab"]
        st.query_params.pop("tab", None)
    if st.query_params.get("tab") in NOTIFY_TABS:
        # linkul vechi ?tab=weekly deschide acum Notificari, cu sub-tabul raportului
        st.session_state["_notify_tab"] = st.query_params["tab"]
        st.query_params["tab"] = "notifications"
    tabs = url_tabs([(i, label) for i, label, _ in entries], "settings_tab")
    for i, _, fn in entries:
        if tabs[i].open is False:
            continue  # se randeaza doar tabul deschis
        with tabs[i]:
            fn()
