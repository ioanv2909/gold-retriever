"""Settings page: Trading 212 keys, user management (admin), about + release notes."""
import json
import os

import streamlit as st

import users
from i18n import LANGS, t
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
        st.segmented_control("Language", LANGS, key="lang", label_visibility="collapsed")

    # (id, eticheta, functie); id-ul apare in URL (?tab=...), deci nu depinde de limba
    entries = [("t212", "🔑 Trading 212", _tab_t212)]
    entries += list(sections)
    if users.role(me) == "admin":
        entries.append(("users", "👥 " + _L("Utilizatori", "Users"), lambda: _tab_users(me)))
    entries.append(("about", "ℹ️ " + _L("Despre", "About"), _tab_about))

    if users.role(me) == "admin":
        from health_ui import render_status
        from notify_ui import render_notifications
        entries.insert(len(entries) - 1, ("notifications", "🔔 " + _L("Notificări", "Notifications"),
                                          lambda: render_notifications(me)))
        entries.insert(len(entries) - 1, ("status", t("hs.tab"), lambda: render_status(me)))
    tabs = url_tabs([(i, label) for i, label, _ in entries], "settings_tab")
    for i, _, fn in entries:
        if tabs[i].open is False:
            continue  # se randeaza doar tabul deschis
        with tabs[i]:
            fn()
