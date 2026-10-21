"""Watchdog pe gazda: verifica health check-ul aplicatiei din cron si anunta adminii cand nu raspunde.

Completeaza logwatch (care ruleaza in aplicatie si nu poate anunta ca aplicatia e cazuta).
Rulat de tools/uptime_check.py; doar biblioteca standard, ca sa mearga si in afara containerului.
"""
import json
import os
import time
import urllib.request

import notify

STATUS_FILE = os.path.join(notify.DATA_ROOT, "uptime_status.json")
HEALTH_URL = os.environ.get("GR_HEALTH_URL", "http://localhost:8501/_stcore/health")
FAILS_TO_ALERT = 2       # doua verificari la rand (la 5 minute: ~10 minute cazuta) inainte de email
CHECK_EVERY = 5 * 60     # intervalul din cron; pagina de stare il foloseste ca sa vada daca watchdog-ul ruleaza


def check(url=HEALTH_URL, timeout=10):
    """(ok, detaliu)."""
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(64).decode("utf-8", "replace").strip()
            ok = r.status == 200 and body == "ok"
            return ok, "HTTP %s %s (%.1f s)" % (r.status, body, time.time() - t0)
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, str(e)[:150])


def step(state, ok, detail, now):
    """Tranzitia starii dupa o verificare. Intoarce (stare noua, (subiect, mesaj) sau None)."""
    state = dict(state or {})
    state["last_check"], state["last_ok_check"] = now, ok
    state["detail"] = detail
    if ok:
        msg = None
        if state.get("alerted"):
            down = now - (state.get("down_since") or now)
            msg = ("Aplicația răspunde din nou",
                   "GoldRetriever răspunde din nou după aproximativ %d minute.\n\n%s" % (round(down / 60), detail))
        state.update(fails=0, down_since=None, alerted=False, last_ok=now)
        return state, msg
    state["fails"] = int(state.get("fails") or 0) + 1
    state["down_since"] = state.get("down_since") or now
    if state["fails"] >= FAILS_TO_ALERT and not state.get("alerted"):
        state["alerted"] = True
        return state, ("Aplicația nu răspunde",
                       "Health check-ul GoldRetriever a eșuat de %d ori la rând (prima dată la %s).\n\nUltima eroare: %s\n"
                       "Verifică pe server: docker ps; docker logs --tail 50 gold-retriever"
                       % (state["fails"], time.strftime("%Y-%m-%d %H:%M", time.localtime(state["down_since"])), detail))
    return state, None


def load():
    try:
        with open(STATUS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def run(now=None):
    """O verificare completa: health check, stare, email la tranzitii. Intoarce codul de iesire pentru cron."""
    now = now or time.time()
    ok, detail = check()
    state, msg = step(load(), ok, detail, now)
    notify._write(STATUS_FILE, state)
    if msg:
        notify.notify("uptime", msg[0], msg[1], key="uptime:%d" % int(now), min_hours=0, sync=True)
    return 0 if ok else 1
