"""Settings -> Notifications (admin): SMTP, admin addresses, events, test email."""
import time

import streamlit as st

import notify
import users


def _L(ro, en):
    return ro if str(st.session_state.get("lang", "")).upper().startswith("RO") else en


def render_notifications(me):
    cfg = notify.load_settings()
    st.caption(_L(
        "Emailuri către admini când ceva eșuează. Folosește o parolă de aplicație, nu parola contului. "
        "Parola SMTP se salvează în clar în data/mail.json (ca și cheile Trading 212).",
        "Emails to admins when something fails. Use an app password, not your account password. "
        "The SMTP password is stored in plain text in data/mail.json (like the Trading 212 keys).",
    ))

    st.markdown("#### " + _L("Adrese admini", "Admin addresses"))
    emails = {}
    for r in users.records():
        if r["role"] != "admin":
            continue
        c1, c2 = st.columns([2, 5], vertical_alignment="center")
        c1.markdown("**%s**" % r["name"])
        emails[r["key"]] = c2.text_input(
            r["name"], value=r.get("email") or "", key="nt_mail_" + r["key"],
            label_visibility="collapsed", placeholder="name@example.com",
        )

    st.markdown("#### SMTP")
    c1, c2, c3 = st.columns([4, 2, 3])
    host = c1.text_input(_L("Server", "Server"), value=cfg["host"], key="nt_host", placeholder="smtp.mail.yahoo.com")
    port = c2.number_input("Port", min_value=1, max_value=65535, value=int(cfg["port"]), key="nt_port")
    opts = ["starttls", "ssl", "none"]
    security = c3.selectbox(
        _L("Criptare", "Security"), opts,
        index=opts.index(cfg["security"]) if cfg["security"] in opts else 0, key="nt_sec",
    )
    c4, c5 = st.columns(2)
    user = c4.text_input(_L("Utilizator", "Username"), value=cfg["user"], key="nt_user")
    pwd = c5.text_input(
        _L("Parolă de aplicație (gol = nemodificată)", "App password (empty = unchanged)"),
        type="password", key="nt_pwd",
    )
    sender = st.text_input(_L("Expeditor (From)", "Sender (From)"), value=cfg["sender"], key="nt_sender",
                           placeholder="you@example.com")

    labels = {
        "backup": _L("Backup eșuat sau lipsă", "Backup failed or missing"),
        "refresh": _L("Actualizări eșuate", "Failed refreshes"),
        "xtb_import": _L("Importuri XTB cu probleme", "XTB imports with problems"),
        "security": _L("Securitate", "Security"),
        "events": _L("Calendar (fiecărui utilizator, la adresa proprie)", "Calendar (to each user, at their own address)"),
        "positions": _L("Alerte poziții: preț, scor, concentrare (fiecărui utilizator)", "Position alerts: price, score, concentration (to each user)"),
    }
    chosen = st.multiselect(
        _L("Evenimente", "Events"), list(labels),
        default=[e for e in cfg["events"] if e in labels],
        format_func=lambda k: labels[k], key="nt_events",
    )
    hours = st.number_input(
        _L("Nu retrimite aceeași alertă mai des de (ore)", "Do not resend the same alert more often than (hours)"),
        min_value=1, max_value=168, value=int(cfg["min_interval_h"]), key="nt_hours",
    )

    b1, b2, _sp = st.columns([2, 3, 5])
    if b1.button("💾 " + _L("Salvează", "Save"), key="nt_save"):
        bad = [k for k, v in emails.items() if users.set_email(k, v)]
        notify.save_settings({
            "host": host.strip(), "port": port, "security": security, "user": user.strip(),
            "password": pwd or cfg["password"], "sender": sender.strip(),
            "events": chosen, "min_interval_h": hours,
        })
        if bad:
            st.error(_L("Adresă de email invalidă pentru: ", "Invalid email address for: ") + ", ".join(bad))
        else:
            st.success(_L("Salvat.", "Saved."))
    if b2.button("✉️ " + _L("Trimite email de test", "Send test email"), key="nt_test"):
        ok, msg = notify.send_test()
        if ok:
            st.success(_L("Trimis la: ", "Sent to: ") + msg)
        else:
            st.error(msg)

    state = notify.last_state()
    if state.get("last_error"):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(state.get("last_ts", 0)))
        st.warning(_L("Ultima eroare de trimitere (", "Last send error (") + when + "): " + state["last_error"])
