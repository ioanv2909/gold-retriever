"""Dispozitive cunoscute per utilizator: la o autentificare de pe un dispozitiv nou adminul primeste un e-mail.

Amprenta = browser + sistem din User-Agent (presence.device, fara versiuni), deci o actualizare de browser nu
alerteaza. Pe disc (data/known_devices.json) stau doar amprenta, eticheta si momentele; nu User-Agent-ul intreg,
nu IP-ul. Prima autentificare a unui cont (lista goala) inregistreaza dispozitivul fara alerta.
"""
import hashlib
import ipaddress
import os
import threading
import time

import alerts
import presence
from core import update_json_file
from userctx import DATA_ROOT

DEVICES_FILE = os.path.join(DATA_ROOT, "known_devices.json")
MAX_DEVICES = 10          # per utilizator; peste limita iese cel folosit cel mai de demult
MAX_ALERTS_PER_HOUR = 3   # per utilizator; dispozitivul se inregistreaza oricum

_lock = threading.Lock()
_alerts = {}              # user -> lista de momente ale alertelor trimise


def fingerprint(ua):
    label = presence.device(ua)
    return hashlib.sha256(label.encode()).hexdigest()[:16], label


def short_ip(ip):
    """IP trunchiat pentru e-mail: 192.168.x.x, sau primele 3 grupuri ale unei adrese IPv6."""
    try:
        a = ipaddress.ip_address(str(ip or "").strip())
    except ValueError:
        return "?"
    if a.version == 4:
        return ".".join(str(a).split(".")[:2]) + ".x.x"
    return ":".join(a.exploded.split(":")[:3]) + "::/48"


def _may_alert(user, now):
    with _lock:
        recent = [t for t in _alerts.get(user, []) if now - t < 3600]
        ok = len(recent) < MAX_ALERTS_PER_HOUR
        if ok:
            recent.append(now)
        _alerts[user] = recent
        return ok


def check_login(user, ua, ip=None, now=None):
    """Inregistreaza dispozitivul la o autentificare reusita. Returneaza "first", "known" sau "new"
    (la "new" se trimite e-mailul de securitate, in limita MAX_ALERTS_PER_HOUR)."""
    user = str(user).lower()
    now = now if now is not None else time.time()
    fp, label = fingerprint(ua)
    result = {}

    def upd(d):
        d = d if isinstance(d, dict) else {}
        devs = [x for x in (d.get(user) or []) if isinstance(x, dict) and x.get("fp")]
        hit = next((x for x in devs if x["fp"] == fp), None)
        if hit:
            hit["last"] = now
            result["status"] = "known"
        else:
            result["status"] = "new" if devs else "first"
            devs.append({"fp": fp, "label": label, "first": now, "last": now})
        devs.sort(key=lambda x: x.get("last", 0), reverse=True)
        d[user] = devs[:MAX_DEVICES]
        return d

    update_json_file(DEVICES_FILE, {}, upd)
    status = result["status"]
    if status == "new" and _may_alert(user, now):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
        alerts.record_user_event("autentificare de pe dispozitiv nou", user, user,
                                 "dispozitiv: %s, ora: %s, IP: %s" % (label, when, short_ip(ip)))
    return status
