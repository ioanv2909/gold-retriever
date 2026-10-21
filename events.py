"""Calendar de evenimente pentru pozitiile detinute: rezultate financiare, ex-dividend, plata dividendului.

Sursa: yfinance Ticker.calendar. Cache comun (pe ticker), preferinte si evidenta emailurilor per utilizator.
"""
import copy
import json
import os
import threading
import time
from datetime import date, datetime, timedelta

from core import load_json_file, read_status, save_json_file, update_json_file
from userctx import UPath, current_user, user_dir

EVENTS_CACHE_FILE = UPath("events_cache.json", shared=True)
EVENTS_STATUS_FILE = UPath("events_status.json", shared=True)
EVENTS_PREFS_FILE = UPath("events_prefs.json")
EVENTS_NOTIFIED_FILE = UPath("events_notified.json")
EVENTS_REFRESH_INTERVAL = 12 * 60 * 60

TYPES = ("earnings", "ex_dividend", "dividend_payment")
DEFAULT_PREFS = {"email": False, "days_ahead": 7}
_FIELDS = {"Ex-Dividend Date": "ex_dividend", "Dividend Date": "dividend_payment"}


def _iso(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str) and len(v) >= 10:
        try:
            return date.fromisoformat(v[:10]).isoformat()
        except ValueError:
            return None
    return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def parse_calendar(cal):
    """Transforma dict-ul din yfinance Ticker.calendar intr-o lista de evenimente."""
    if not isinstance(cal, dict):
        return []
    out = []
    dates = cal.get("Earnings Date")
    dates = [d for d in (dates if isinstance(dates, (list, tuple)) else [dates]) if _iso(d)]
    if dates:
        ev = {"type": "earnings", "date": _iso(dates[0])}
        if len(dates) > 1 and _iso(dates[-1]) != ev["date"]:
            ev["date_end"] = _iso(dates[-1])
        for src, dst in (("Earnings Average", "eps_avg"), ("Revenue Average", "revenue_avg")):
            if _num(cal.get(src)) is not None:
                ev[dst] = _num(cal.get(src))
        out.append(ev)
    for src, typ in _FIELDS.items():
        d = _iso(cal.get(src))
        if d:
            out.append({"type": typ, "date": d})
    return out


def fetch_events(yahoo_symbol):
    from yf_compat import yf, YFINANCE_AVAILABLE
    if not YFINANCE_AVAILABLE:
        return None, "yfinance indisponibil"
    try:
        return parse_calendar(yf.Ticker(yahoo_symbol).calendar), None
    except Exception as e:
        return None, str(e)[:200]


def load_cache():
    return load_json_file(EVENTS_CACHE_FILE, {})


def load_status():
    return read_status(EVENTS_STATUS_FILE)


def fetch_and_cache_events(tickers, resolve=None, now=None, sleep=1.0):
    """Actualizeaza cache-ul pentru tickerele date; sare peste cele actualizate in ultimele 12 ore."""
    if resolve is None:
        from yahoo import resolve_yahoo_symbol as resolve
    now = now if now is not None else time.time()
    total = len(tickers)
    save_json_file(EVENTS_STATUS_FILE, {"in_progress": True, "started_at": now, "total": total, "done": 0})
    cache = load_cache()
    try:
        for idx, ticker in enumerate(tickers):
            fetched = (cache.get(ticker) or {}).get("fetched_at")
            if fetched is None or now - float(fetched) >= EVENTS_REFRESH_INTERVAL:
                symbol = resolve(ticker)
                events, err = fetch_events(symbol)
                # si erorile se salveaza (ETF-urile dau 404), ca sa nu reincercam la fiecare tur
                cache[ticker] = {"symbol": symbol, "events": events or [], "fetched_at": now}
                if err:
                    cache[ticker]["error"] = err
                # alt utilizator poate scrie in acelasi timp: actualizeaza doar intrarea proprie
                update_json_file(EVENTS_CACHE_FILE, {}, lambda c, t=ticker: dict(c, **{t: cache[t]}))
                if sleep and idx < total - 1:
                    time.sleep(sleep)
            save_json_file(EVENTS_STATUS_FILE, {"in_progress": True, "started_at": None, "total": total, "done": idx + 1})
    finally:
        save_json_file(EVENTS_STATUS_FILE, {"in_progress": False, "started_at": None, "total": total, "done": total})
    return cache


def start_events_fetch_background(tickers):
    if load_status().get("in_progress"):
        return False
    threading.Thread(target=fetch_and_cache_events, args=(list(tickers),), daemon=True).start()
    return True


def upcoming(cache, tickers, today=None, days=60):
    """Evenimentele dintre azi si azi+days pentru tickerele date, sortate dupa data."""
    today = today or date.today()
    start, end = today.isoformat(), (today + timedelta(days=days)).isoformat()
    out = []
    for ticker in dict.fromkeys(tickers):
        for ev in (cache.get(ticker) or {}).get("events") or []:
            last = ev.get("date_end") or ev.get("date")
            if ev.get("type") in TYPES and ev.get("date") and last >= start and ev["date"] <= end:
                row = dict(ev, ticker=ticker)
                row["days"] = (date.fromisoformat(ev["date"]) - today).days
                out.append(row)
    return sorted(out, key=lambda r: (r["date"], r["ticker"], TYPES.index(r["type"])))


def event_id(ev):
    return "%s|%s|%s" % (ev["ticker"], ev["type"], ev["date"])


def load_prefs():
    prefs = copy.deepcopy(DEFAULT_PREFS)
    saved = load_json_file(EVENTS_PREFS_FILE, {})
    if isinstance(saved, dict):
        prefs.update({k: saved[k] for k in DEFAULT_PREFS if k in saved})
    return prefs


def save_prefs(email, days_ahead):
    prefs = {"email": bool(email), "days_ahead": max(1, min(30, int(days_ahead)))}
    save_json_file(EVENTS_PREFS_FILE, prefs)
    return prefs


def _user_lang():
    try:
        with open(os.path.join(user_dir(), "ui_prefs.json"), encoding="utf-8") as f:
            return "EN" if str(json.load(f).get("lang", "")).upper() == "EN" else "RO"
    except Exception:
        return "RO"


def format_digest(events, lang="RO"):
    from i18n import t
    lines = []
    for ev in events:
        when = ev["date"] + (" - " + ev["date_end"] if ev.get("date_end") else "")
        line = "%s  %-10s  %s" % (when, ev["ticker"], t("ev.type." + ev["type"], _lang=lang))
        if ev.get("eps_avg") is not None:
            line += "  (" + t("ev.eps_est", _lang=lang, v="%.2f" % ev["eps_avg"]) + ")"
        lines.append(line)
    return t("ev.mail_intro", _lang=lang) + "\n\n" + "\n".join(lines)


def notify_upcoming(tickers, user=None, today=None, cache=None):
    """Trimite utilizatorului un email cu evenimentele noi din urmatoarele zile. Fiecare eveniment o singura data."""
    import notify
    import users
    from i18n import t

    prefs = load_prefs()
    if not prefs["email"]:
        return False
    user = user or current_user()
    email = users.email(user) if user else None
    if not email:
        return False
    today = today or date.today()
    events = upcoming(cache if cache is not None else load_cache(), tickers, today, prefs["days_ahead"])
    sent = {k: v for k, v in load_json_file(EVENTS_NOTIFIED_FILE, {}).items() if v >= (today - timedelta(days=7)).isoformat()}
    new = [ev for ev in events if event_id(ev) not in sent]
    if not new:
        return False
    lang = _user_lang()
    subject = t("ev.mail_subject", _lang=lang, n=len(new))
    ok = notify.notify("events", subject, format_digest(new, lang), to=[email], sync=True,
                       key="events:%s:%s" % (user, today.isoformat()), min_hours=0)
    if ok:
        sent.update({event_id(ev): ev.get("date_end") or ev["date"] for ev in new})
        save_json_file(EVENTS_NOTIFIED_FILE, sent)
    return ok
