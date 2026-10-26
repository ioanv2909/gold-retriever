"""Registru de prezenta: sesiunile autentificate vazute recent (pentru adminii din Setari -> Utilizatori).

Autentificarea e fara stare (cookie semnat), deci fiecare sesiune Streamlit autentificata primeste un id aleator
si isi actualizeaza aici inregistrarea, cel mult o data la WRITE_EVERY secunde. Nu se stocheaza parole,
token-uri, cookie-uri sau alte antete in afara de User-Agent.
"""
import os
import threading
import time

from core import load_json_file, update_json_file
from userctx import DATA_ROOT

PRESENCE_FILE = os.path.join(DATA_ROOT, "presence.json")
WRITE_EVERY = 45          # secunde intre doua scrieri pe disc pentru aceeasi sesiune
ONLINE_WINDOW = 5 * 60    # "conectat" = vazut in ultimele 5 minute
KEEP = 24 * 3600          # inregistrarile mai vechi se sterg
_UA_MAX = 300

_lock = threading.Lock()
_written = {}             # sid -> (ts ultima scriere, utilizator)


def _prune(sessions, now):
    return {k: v for k, v in sessions.items() if isinstance(v, dict) and now - float(v.get("last", 0)) <= KEEP}


def touch(sid, user, ua=None, ip=None, now=None):
    """Actualizeaza sesiunea sid. Returneaza True daca s-a scris pe disc."""
    if not sid or not user:
        return False
    now = now if now is not None else time.time()
    user = str(user).lower()
    with _lock:
        prev = _written.get(sid)
        if prev and prev[1] == user and now - prev[0] < WRITE_EVERY:
            return False
        _written[sid] = (now, user)
        for k in [k for k, (ts, _) in _written.items() if now - ts > KEEP]:
            _written.pop(k, None)

    def upd(d):
        sessions = _prune(d.get("sessions") or {}, now)
        rec = sessions.get(sid)
        if not rec or rec.get("user") != user:
            rec = {"user": user, "first": now}
        rec.update(last=now, ua=str(ua or "")[:_UA_MAX], ip=str(ip or "")[:64])
        sessions[sid] = rec
        return {"sessions": sessions}

    update_json_file(PRESENCE_FILE, {}, upd)
    return True


def _drop(match):
    with _lock:
        for k in [k for k, v in _written.items() if match(k, {"user": v[1]})]:
            _written.pop(k, None)
    update_json_file(PRESENCE_FILE, {}, lambda d: {
        "sessions": {k: v for k, v in _prune(d.get("sessions") or {}, time.time()).items() if not match(k, v)}})


def forget_session(sid):
    if sid:
        _drop(lambda k, v: k == sid)


def forget_user(user):
    user = str(user).lower()
    _drop(lambda k, v: v.get("user") == user)


def sessions(now=None):
    now = now if now is not None else time.time()
    return _prune(load_json_file(PRESENCE_FILE, {}).get("sessions") or {}, now)


def online(now=None, window=ONLINE_WINDOW):
    """Un rand per utilizator conectat, sortat dupa ultima activitate (cea mai recenta prima)."""
    now = now if now is not None else time.time()
    by = {}
    for rec in sessions(now).values():
        if now - float(rec.get("last", 0)) > window:
            continue
        u = rec.get("user")
        row = by.get(u)
        if row is None:
            row = by[u] = {"user": u, "first": rec["first"], "last": -1, "ua": "", "ip": "", "sessions": 0}
        row["sessions"] += 1
        row["first"] = min(row["first"], rec.get("first", rec["last"]))
        if rec["last"] > row["last"]:
            row.update(last=rec["last"], ua=rec.get("ua", ""), ip=rec.get("ip", ""))
    return sorted(by.values(), key=lambda r: r["last"], reverse=True)


_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("FxiOS", "Firefox"),
             ("CriOS", "Chrome"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
_SYSTEMS = (("Android", "Android"), ("iPhone", "iOS"), ("iPad", "iPadOS"), ("Windows", "Windows"),
            ("Mac OS X", "macOS"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))


def device(ua):
    """Eticheta scurta "Browser / Sistem" din User-Agent (dupa cuvinte cheie)."""
    ua = str(ua or "")
    b = next((n for k, n in _BROWSERS if k in ua), "")
    s = next((n for k, n in _SYSTEMS if k in ua), "")
    return " / ".join(x for x in (b, s) if x) or (ua[:40] if ua else "?")
