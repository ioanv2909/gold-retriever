"""Watchdog pe log: prinde erorile scrise pe stdout/stderr, le grupeaza dupa tipar si anunta adminii.

Ruleaza in procesul aplicatiei, deci nu vede nimic daca procesul e cazut. Un tipar nou (nevazut in ultimele
24 de ore) declanseaza un email catre admini, cel mult unul la 30 de minute. Lista e in Setari -> Notificari.
"""
import collections
import json
import logging
import os
import re
import sys
import threading
import time

import notify

PROBLEMS_FILE = os.path.join(notify.DATA_ROOT, "log_problems.json")
WINDOW = 24 * 3600        # un tipar e "nou" daca nu a aparut in ultimele 24 de ore
MAIL_EVERY = 30 * 60      # cel mult un email la 30 de minute
FLUSH_EVERY = 60
KEEP = 100
TAIL = 1000               # ultimele linii din log, in memorie (Setari -> Log)

# o linie e problema daca se potriveste cu PROBLEM si nu cu IGNORE
PROBLEM = re.compile(r"Traceback \(most recent call last\)|HTTP Error \d{3}|^\[[a-z_]+\] |\bERROR\b|Exception\b|Error:")
IGNORE = re.compile(
    r"Cookie fetch from fc\.yahoo\.com failed|missing ScriptRunContext|No runtime found|"
    r"HTTP Error 404|No fundamentals data found|possibly delisted|"
    r"Session state does not function|\[yf_compat\] HTTP 401|"
    r"^Exception in thread "  # urmeaza traceback-ul, care se inregistreaza separat
)
_SIG_SUBS = [
    (re.compile(r"\{.*\}"), "{...}"),                      # corpuri JSON din raspunsuri
    (re.compile(r"(symbol|isin|ticker)[:= ]+\S+", re.I), r"\1 <x>"),
    (re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b"), "<isin>"),
    (re.compile(r"\d+(\.\d+)?"), "#"),
    (re.compile(r"\s+"), " "),
]

_lock = threading.Lock()
_problems = {}           # semnatura -> {count, first, last, sample, new}
_state = {"last_mail": None, "dirty": False, "installed": False}
_tail = collections.deque(maxlen=TAIL)   # (ts, linie)


def signature(line):
    s = line.strip()
    for rx, rep in _SIG_SUBS:
        s = rx.sub(rep, s)
    return s[:160]


INFO = re.compile(r"^\[auth\] ")  # evenimente de autentificare: apar in Setari -> Log, dar nu sunt erori


def is_problem(line):
    return bool(PROBLEM.search(line)) and not IGNORE.search(line) and not INFO.search(line)


def record(line, now=None):
    """Inregistreaza o linie de log daca e problema. Intoarce semnatura sau None."""
    if not line or not line.strip() or not is_problem(line):
        return None
    now = now or time.time()
    sig = signature(line)
    with _lock:
        p = _problems.get(sig)
        if p is None or now - p["last"] > WINDOW:
            p = _problems[sig] = {"count": 0, "first": now, "last": now, "sample": "", "new": True}
        p["count"] += 1
        p["last"] = now
        p["sample"] = line.strip()[:300]
        _state["dirty"] = True
    return sig


class _Tee:
    """Scrie mai departe in stream-ul original si trimite fiecare linie completa la record().
    Un traceback se inregistreaza o singura data, cu ultima lui linie (exceptia)."""

    def __init__(self, stream):
        self._stream = stream
        self._buf = ""
        self._in_tb = False
        self._lk = threading.Lock()

    def write(self, data):
        n = self._stream.write(data)
        try:
            with self._lk:
                self._buf += data
                *lines, self._buf = self._buf.split("\n")
                for line in lines:
                    self._line(line)
        except Exception:
            pass
        return n

    def _line(self, line):
        line = line.rstrip("\r")
        if line.strip():
            _tail.append((time.time(), line))
        if line.startswith("Traceback (most recent call last)"):
            self._in_tb = True
            return
        if self._in_tb:
            if line.startswith((" ", "\t")) or not line.strip():
                return
            self._in_tb = False
            record("Traceback: " + line)
            return
        record(line)

    def flush(self):
        return self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _load():
    try:
        with open(PROBLEMS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def flush(now=None, send=True):
    """Salveaza lista si, daca exista tipare noi si a trecut intervalul, trimite un email adminilor."""
    now = now or time.time()
    with _lock:
        for sig in [s for s, p in _problems.items() if now - p["last"] > WINDOW]:
            del _problems[sig]
        new = {s: dict(p) for s, p in _problems.items() if p["new"]}
        last = _state["last_mail"]
        mail_due = bool(new) and send and (last is None or now - last >= MAIL_EVERY)
        if mail_due:
            for s in new:
                _problems[s]["new"] = False
            _state["last_mail"] = now
        if not (_state["dirty"] or mail_due):
            return False
        _state["dirty"] = False
        snapshot = dict(sorted(_problems.items(), key=lambda kv: -kv[1]["last"])[:KEEP])
    try:
        notify._write(PROBLEMS_FILE, {"updated": now, "problems": snapshot})
    except Exception:
        pass
    if mail_due:
        lines = ["%d× %s" % (p["count"], p["sample"]) for p in sorted(new.values(), key=lambda p: -p["count"])]
        body = "Erori noi în log (%d tipare):\n\n%s\n\nLista completă: Setări → Notificări → Probleme recente." % (
            len(new), "\n\n".join(lines[:20]))
        notify.notify("logs", "Erori noi în log (%d)" % len(new), body, key="logs:%d" % int(now), min_hours=0)
    return True


def recent():
    """Lista salvata (pentru Setari), cea mai recenta prima."""
    data = _load().get("problems") or {}
    return sorted(data.values(), key=lambda p: -p.get("last", 0))


def tail(n=TAIL, hide_noise=False, query="", newest_first=False):
    """Ultimele n linii din log, cu ora la care au fost scrise; implicit cele mai vechi primele."""
    rows = list(_tail)
    if hide_noise:
        rows = [r for r in rows if not IGNORE.search(r[1])]
    if query:
        q = query.lower()
        rows = [r for r in rows if q in r[1].lower()]
    rows = rows[-n:]
    if newest_first:
        rows.reverse()
    return ["%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)), line) for ts, line in rows]


def clear():
    with _lock:
        _problems.clear()
        _state["dirty"] = True
    flush(send=False)


def _redirect_log_handlers(by_id):
    """Handler-ele logging create inainte (Streamlit, yfinance) tin referinta la stream-ul original; le trecem prin tee."""
    loggers = [logging.getLogger()] + [l for l in logging.root.manager.loggerDict.values() if isinstance(l, logging.Logger)]
    for lg in loggers:
        for h in lg.handlers:
            stream = getattr(h, "stream", None)
            if isinstance(h, logging.StreamHandler) and id(stream) in by_id:
                h.setStream(by_id[id(stream)])


def install():
    """O singura data per proces: tee pe stdout/stderr si firul care salveaza / trimite."""
    with _lock:
        if _state["installed"]:
            return False
        _state["installed"] = True
    for name, saved in _load().get("problems", {}).items():
        saved = dict(saved, new=False)  # ce s-a vazut inainte de restart nu mai e nou
        _problems.setdefault(name, saved)
    orig_out, orig_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Tee(orig_out), _Tee(orig_err)
    _redirect_log_handlers({id(orig_out): sys.stdout, id(orig_err): sys.stderr})

    def loop():
        while True:
            time.sleep(FLUSH_EVERY)
            try:
                flush()
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True, name="logwatch").start()
    return True
