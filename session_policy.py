"""Expirarea sesiunilor: inactivitate maxima si durata absoluta a cookie-ului de autentificare.

Valorile implicite sunt aici; un admin le poate schimba din Setari -> Utilizatori -> Sesiuni
(data/session_policy.json). Activitatea fiecarui cookie se tine pe server in data/session_activity.json,
cheia fiind un hash scurt al semnaturii (token-ul nu se stocheaza). Functiile primesc `now` ca sa poata fi
testate cu timp simulat.
"""
import hashlib
import os
import threading
import time

from core import load_json_file, save_json_file, update_json_file
from userctx import DATA_ROOT

DEFAULT_IDLE_HOURS = 8
DEFAULT_MAX_DAYS = 30
IDLE_RANGE = (1, 720)     # ore
MAX_DAYS_RANGE = (1, 365)  # zile
WRITE_EVERY = 5 * 60      # secunde intre doua scrieri ale activitatii aceluiasi cookie

POLICY_FILE = os.path.join(DATA_ROOT, "session_policy.json")
ACTIVITY_FILE = os.path.join(DATA_ROOT, "session_activity.json")

_lock = threading.Lock()
_written = {}             # id token -> ts ultima scriere
_cache = {"key": None, "val": None}


def _valid(v, rng):
    return isinstance(v, int) and not isinstance(v, bool) and rng[0] <= v <= rng[1]


def limits():
    """(ore de inactivitate, zile durata absoluta): setarea adminului sau valorile implicite."""
    try:
        st = os.stat(POLICY_FILE)
        key = (POLICY_FILE, st.st_mtime_ns, st.st_size)
    except OSError:
        return DEFAULT_IDLE_HOURS, DEFAULT_MAX_DAYS
    if _cache["key"] != key:
        d = load_json_file(POLICY_FILE, {})
        d = d if isinstance(d, dict) else {}
        idle = d.get("idle_hours")
        days = d.get("max_days")
        _cache["val"] = (idle if _valid(idle, IDLE_RANGE) else DEFAULT_IDLE_HOURS,
                         days if _valid(days, MAX_DAYS_RANGE) else DEFAULT_MAX_DAYS)
        _cache["key"] = key
    return _cache["val"]


def save_limits(idle_hours, max_days):
    """Salveaza setarea adminului. Returneaza None sau un cod de eroare ("idle", "days")."""
    if not _valid(idle_hours, IDLE_RANGE):
        return "idle"
    if not _valid(max_days, MAX_DAYS_RANGE):
        return "days"
    save_json_file(POLICY_FILE, {"idle_hours": idle_hours, "max_days": max_days}, raise_errors=True)
    return None


def reset_limits():
    save_json_file(POLICY_FILE, {}, raise_errors=True)


def max_seconds():
    return limits()[1] * 86400


def idle_seconds():
    return limits()[0] * 3600


def token_expired(exp, now=None):
    """Cookie expirat: data din token a trecut sau e mai departe decat permite limita curenta."""
    now = now if now is not None else time.time()
    return exp < now or exp > now + max_seconds() + 60


def is_idle(last, now=None):
    now = now if now is not None else time.time()
    return last is not None and now - last > idle_seconds()


def token_id(token):
    """Id scurt al unui cookie (hash al semnaturii); token-ul insusi nu ajunge pe disc."""
    sig = str(token or "").rsplit(".", 1)[-1]
    return hashlib.sha256(sig.encode()).hexdigest()[:24] if sig else None


def _ts(v):
    """Momentul unei intrari: numar = ultima activitate, {"revoked": ts} = cookie scos la deconectare."""
    if isinstance(v, dict):
        v = v.get("revoked")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _prune(d, now):
    keep = max_seconds()
    return {k: v for k, v in (d if isinstance(d, dict) else {}).items()
            if _ts(v) is not None and now - _ts(v) <= keep}


def last_activity(tid):
    """Ultima activitate inregistrata pentru cookie; 0 pentru un cookie scos la deconectare (mereu inactiv);
    None pentru un cookie emis inainte de registru (considerat activ)."""
    if not tid:
        return None
    v = (load_json_file(ACTIVITY_FILE, {}) or {}).get(tid)
    if isinstance(v, dict):
        return 0.0
    return _ts(v)


def touch(tid, now=None, force=False):
    """Inregistreaza activitate pentru cookie, cel mult o data la WRITE_EVERY. Returneaza True daca a scris."""
    if not tid:
        return False
    now = now if now is not None else time.time()
    with _lock:
        prev = _written.get(tid)
        if not force and prev is not None and now - prev < WRITE_EVERY:
            return False
        _written[tid] = now

    def upd(d):
        d = _prune(d, now)
        if not isinstance(d.get(tid), dict):  # un cookie scos ramane scos
            d[tid] = now
        return d

    update_json_file(ACTIVITY_FILE, {}, upd)
    return True


def revoke(tid, now=None):
    """La deconectare: cookie-ul nu mai poate redeschide o sesiune, chiar daca a ramas in browser."""
    if not tid:
        return
    now = now if now is not None else time.time()
    with _lock:
        _written.pop(tid, None)

    def upd(d):
        d = _prune(d, now)
        d[tid] = {"revoked": now}
        return d

    update_json_file(ACTIVITY_FILE, {}, upd)
