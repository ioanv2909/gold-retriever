"""Starea serviciilor externe (Yahoo, justETF, Trading 212, SMTP), masurata pe cererile reale ale aplicatiei.

record() se apeleaza din punctele unde pleaca cererile; status() da nivelul pentru pagina Setari -> Stare:
green (merge), yellow (erori recente, dar ultima cerere a mers), red (nu merge), gray (fara date inca).
"""
import collections
import json
import os
import threading
import time

DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
HEALTH_FILE = os.path.join(DATA_ROOT, "service_status.json")
SOURCES = ("yahoo", "justetf", "t212", "smtp")
KEEP = 300               # ultimele evenimente per sursa
HOUR = 3600
RED_AFTER = 15 * 60      # rosu daca ultima cerere a esuat si nu a mers nimic in ultimele 15 minute
SAVE_EVERY = 30

_lock = threading.Lock()
_events = {s: collections.deque(maxlen=KEEP) for s in SOURCES}    # (ts, ok, ms)
_last = {s: {"ok": None, "fail": None, "error": None} for s in SOURCES}
_saved = {"at": 0.0, "loaded": False}


def record(source, ok, duration=None, error=None, now=None):
    if source not in _events:
        return
    now = now or time.time()
    with _lock:
        _ensure_loaded()
        _events[source].append((now, bool(ok), round(duration * 1000) if duration is not None else None))
        if ok:
            _last[source]["ok"] = now
        else:
            _last[source]["fail"] = now
            _last[source]["error"] = str(error or "")[:300]
        due = now - _saved["at"] >= SAVE_EVERY
    if due:
        save(now)


class timed:
    """with health.timed("yahoo") as h: ...; h.ok = False (sau o exceptie) marcheaza esecul."""

    def __init__(self, source):
        self.source, self.ok, self.error = source, True, None

    def __enter__(self):
        self._t = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        ok = self.ok and exc is None
        record(self.source, ok, time.time() - self._t, self.error or (exc and "%s: %s" % (type(exc).__name__, exc)))
        return False


def status(source, now=None):
    now = now or time.time()
    with _lock:
        _ensure_loaded()
        ev = list(_events.get(source, ()))
        last = dict(_last.get(source, {}))
    hour = [e for e in ev if now - e[0] <= HOUR]
    out = {
        "level": "gray", "last_ok": last.get("ok"), "last_fail": last.get("fail"), "error": last.get("error"),
        "n_1h": len(hour), "fail_1h": sum(1 for e in hour if not e[1]),
        "avg_ms_1h": (sum(e[2] for e in hour if e[2] is not None) / max(1, sum(1 for e in hour if e[2] is not None)))
        if hour else None,
    }
    if not ev:
        return out
    last_ok, last_fail = last.get("ok") or 0, last.get("fail") or 0
    if last_fail > last_ok and now - last_ok > RED_AFTER:
        out["level"] = "red"
    elif out["fail_1h"]:
        out["level"] = "yellow"
    else:
        out["level"] = "green"
    return out


def save(now=None):
    now = now or time.time()
    with _lock:
        data = {"saved": now, "events": {s: list(_events[s]) for s in SOURCES}, "last": _last}
        _saved["at"] = now
        payload = json.dumps(data)
    try:
        os.makedirs(os.path.dirname(HEALTH_FILE), exist_ok=True)
        tmp = HEALTH_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, HEALTH_FILE)
    except Exception:
        pass


def _ensure_loaded():
    """Incarca o singura data istoricul salvat (supravietuieste unui restart). Se apeleaza sub _lock."""
    if _saved["loaded"]:
        return
    _saved["loaded"] = True
    try:
        with open(HEALTH_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for s in SOURCES:
        for e in (data.get("events") or {}).get(s) or []:
            if isinstance(e, list) and len(e) == 3:
                _events[s].append(tuple(e))
        saved_last = (data.get("last") or {}).get(s)
        if isinstance(saved_last, dict):
            _last[s].update({k: saved_last.get(k) for k in ("ok", "fail", "error")})


def job_level(raw, effective, mtime, interval, now=None):
    """Starea unui job din fundal, din fisierul lui de status.
    raw: continutul fisierului; effective: dupa read_status (care marcheaza joburile blocate/moarte ca stale)."""
    now = now or time.time()
    if mtime is None:
        return "gray", "never"
    if effective.get("in_progress"):
        return "green", "running"
    if raw.get("in_progress"):
        return "red", "stuck"  # a ramas "in curs" dar nu mai ruleaza (blocat sau oprit)
    if now - mtime <= 2 * interval + 600:
        return "green", "fresh"
    return "yellow", "old"


# ---------------------------------------------------------------------------
# Teste active ("Testeaza acum"): cate o cerere reala; rezultatul intra si in record() prin hook-uri
# ---------------------------------------------------------------------------
def probe_yahoo():
    from yf_compat import yf, YFINANCE_AVAILABLE
    if not YFINANCE_AVAILABLE:
        return False, "yfinance not installed"
    try:
        h = yf.Ticker("AAPL").history(period="5d")
        return (not h.empty), ("AAPL: %d rows" % len(h)) if not h.empty else "empty answer"
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:200])


def probe_justetf():
    from exposure import _TimeoutSession
    try:
        r = _TimeoutSession().get("https://www.justetf.com/en/etf-profile.html?isin=IE00B5BMR087",
                                  headers={"User-Agent": "Mozilla/5.0"})
        return r.status_code == 200, "HTTP %s" % r.status_code
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:200])


def probe_t212():
    """Cerere la account/info cu cheile utilizatorului curent (limita T212: 1 cerere / 30 s)."""
    import requests
    from core import BASE_URL, load_config
    from t212_api import _headers
    cfg = load_config()
    if not cfg.get("api_key_id") or not cfg.get("api_secret"):
        return None, "no Trading 212 keys for this user"
    with timed("t212") as t:
        try:
            r = requests.get(f"{BASE_URL}/equity/account/info", headers=_headers(cfg["api_key_id"], cfg["api_secret"]),
                             timeout=15)
        except Exception as e:
            t.ok, t.error = False, "%s: %s" % (type(e).__name__, str(e)[:150])
            return False, t.error
        t.ok = r.status_code == 200
        t.error = None if t.ok else "HTTP %s" % r.status_code
        if r.status_code == 429:
            return False, "HTTP 429: rate limit, try again in 30 s"
        return t.ok, "HTTP %s" % r.status_code


def probe_smtp():
    import notify
    return notify.check_connection()
