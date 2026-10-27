"""Notificari prin email (SMTP) pentru admini. Doar biblioteca standard, ca sa poata rula si pe gazda.

Setari: data/mail.json (parola SMTP in clar, fisier 0600).
Destinatari: adresele adminilor din data/users.json.
"""
import json
import os
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from email.utils import formatdate

DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MAIL_FILE = os.path.join(DATA_ROOT, "mail.json")
STATE_FILE = os.path.join(DATA_ROOT, "notify_state.json")
USERS_FILE = os.path.join(DATA_ROOT, "users.json")

EVENTS = ("backup", "refresh", "xtb_import", "security", "events", "positions", "logs", "uptime", "weekly")
# evenimentele aparute dupa ce adminul a salvat setarile sunt pornite implicit (altfel lista salvata le-ar opri tacut)
_KNOWN_BEFORE_V0_3_26 = ("backup", "refresh", "xtb_import", "security", "events", "positions", "logs", "uptime")
DEFAULTS = {
    "host": "", "port": 587, "security": "starttls",
    "user": "", "password": "", "sender": "",
    "events": list(EVENTS), "min_interval_h": 6,
}
_LOCK = threading.Lock()


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    try:
        if os.geteuid() == 0:  # rulat ca root pe gazda: pastreaza proprietarul folderului data/
            st = os.stat(os.path.dirname(path))
            os.chown(path, st.st_uid, st.st_gid)
    except Exception:
        pass


def load_settings():
    cfg = dict(DEFAULTS)
    cfg["events"] = list(EVENTS)
    saved = _read(MAIL_FILE, {})
    if isinstance(saved, dict):
        cfg.update({k: saved[k] for k in DEFAULTS if k in saved})
        known = saved.get("events_known") or _KNOWN_BEFORE_V0_3_26
        cfg["events"] = list(cfg["events"]) + [e for e in EVENTS if e not in known and e not in cfg["events"]]
    return cfg


def save_settings(new):
    cfg = load_settings()
    cfg.update({k: new[k] for k in DEFAULTS if k in new})
    cfg["port"] = int(cfg["port"])
    cfg["min_interval_h"] = max(1, int(cfg["min_interval_h"]))
    if cfg["security"] not in ("starttls", "ssl", "none"):
        cfg["security"] = "starttls"
    cfg["events"] = [e for e in cfg["events"] if e in EVENTS]
    _write(MAIL_FILE, dict(cfg, events_known=list(EVENTS)))
    return cfg


def configured(cfg=None):
    cfg = cfg or load_settings()
    return bool(cfg.get("host") and cfg.get("sender"))


def recipients():
    found = (_read(USERS_FILE, {}).get("users") or {}).values()
    return sorted({
        (u.get("email") or "").strip()
        for u in found
        if u.get("role") == "admin" and (u.get("email") or "").strip()
    })


def last_state():
    return _read(STATE_FILE, {})


def _result(err):
    try:
        import health
        health.record("smtp", err is None, error=err)
    except Exception:
        pass
    with _LOCK:
        state = _read(STATE_FILE, {})
        state["last_error"] = err
        state["last_ts"] = time.time()
        _write(STATE_FILE, state)


def _send(cfg, to, subject, body):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    host, port = cfg["host"], int(cfg["port"])
    ctx = ssl.create_default_context()
    if cfg["security"] == "ssl":
        smtp = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20)
    else:
        smtp = smtplib.SMTP(host, port, timeout=20)
    with smtp:
        if cfg["security"] == "starttls":
            smtp.starttls(context=ctx)
        if cfg["user"]:
            smtp.login(cfg["user"], cfg["password"])
        smtp.send_message(msg)


def check_connection():
    """Conectare si autentificare la serverul SMTP, fara sa trimita nimic. Intoarce (ok, mesaj)."""
    cfg = load_settings()
    if not configured(cfg):
        return False, "SMTP not configured (server and sender are required)"
    try:
        ctx = ssl.create_default_context()
        if cfg["security"] == "ssl":
            smtp = smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), context=ctx, timeout=20)
        else:
            smtp = smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=20)
        with smtp:
            if cfg["security"] == "starttls":
                smtp.starttls(context=ctx)
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"])
            smtp.noop()
        _result(None)
        return True, "%s:%s" % (cfg["host"], cfg["port"])
    except Exception as e:
        msg = ("%s: %s" % (type(e).__name__, e))[:300]
        _result(msg)
        return False, msg


def send_test():
    cfg = load_settings()
    if not configured(cfg):
        return False, "SMTP not configured (server and sender are required)"
    to = recipients()
    if not to:
        return False, "No admin has an email address"
    try:
        _send(cfg, to, "[GoldRetriever] Test", "This is a test message from GoldRetriever.")
        _result(None)
        return True, ", ".join(to)
    except Exception as e:
        msg = ("%s: %s" % (type(e).__name__, e))[:300]
        _result(msg)
        return False, msg


def notify(event, subject, body, key=None, sync=False, min_hours=None, to=None):
    """Trimite o alerta adminilor (sau adreselor din `to`). Intoarce True daca a fost trimisa (sau pornita)."""
    cfg = load_settings()
    if event not in cfg["events"] or not configured(cfg):
        return False
    to = list(to) if to else recipients()
    if not to:
        return False
    key = key or "%s:%s" % (event, subject)
    now = time.time()
    with _LOCK:
        state = _read(STATE_FILE, {})
        sent = {k: v for k, v in (state.get("sent") or {}).items() if now - float(v) < 7 * 86400}
        limit_h = cfg["min_interval_h"] if min_hours is None else min_hours
        if now - float(sent.get(key, 0)) < limit_h * 3600:
            return False
        sent[key] = now
        state["sent"] = sent
        _write(STATE_FILE, state)

    def run():
        try:
            _send(cfg, to, "[GoldRetriever] " + subject, body + "\n\n-- GoldRetriever")
            _result(None)
            return True
        except Exception as e:
            _result(("%s: %s" % (type(e).__name__, e))[:300])
            return False

    if sync:
        return run()
    threading.Thread(target=run, daemon=True).start()
    return True
