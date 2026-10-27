"""Raport saptamanal pe email, per utilizator (optional): valoarea portofoliului acum si acum 7 zile,
rezultatul saptamanii (fara depuneri), cele mai mari cresteri/scaderi pe 7 zile, dividendele incasate de la
raportul trecut si evenimentele din urmatoarele 7 zile. Pleaca o data pe saptamana, in ziua si dupa ora alese."""
import copy
import time
from datetime import date, datetime, timedelta

from core import load_json_file, save_json_file
from userctx import UPath

PREFS_FILE = UPath("weekly_report.json")
STATE_FILE = UPath("weekly_report_state.json")
DEFAULT_PREFS = {"enabled": False, "weekday": 5, "hour": 9}  # sambata, dupa ora 09:00
TOP = 3


def load_prefs():
    prefs = copy.deepcopy(DEFAULT_PREFS)
    saved = load_json_file(PREFS_FILE, {})
    if isinstance(saved, dict):
        prefs.update({k: saved[k] for k in DEFAULT_PREFS if k in saved})
    return prefs


def save_prefs(enabled, weekday, hour):
    prefs = {"enabled": bool(enabled), "weekday": int(weekday) % 7, "hour": max(0, min(23, int(hour)))}
    save_json_file(PREFS_FILE, prefs)
    return prefs


def _load_state():
    state = load_json_file(STATE_FILE, {})
    return state if isinstance(state, dict) else {}


def week_key(day):
    y, w, _ = day.isocalendar()
    return "%d-W%02d" % (y, w)


def value_summary(now=None):
    """Valoarea acum si acum ~7 zile, din istoricul pe toate portofoliile; None fara cel putin doua puncte."""
    from history_multi import load_multi_history, multi_history_records
    history = load_multi_history()
    if not history:
        return None
    labels = sorted((history[-1].get("entries") or {}).keys())
    if not labels:
        return None
    entries = history[-1]["entries"]
    ccy = (entries.get("Trading 212") or entries[labels[0]]).get("ccy") or "EUR"
    points = multi_history_records(labels, ccy)
    if len(points) < 2:
        return None
    now = now or datetime.now()
    cutoff = (now - timedelta(days=7)).isoformat()
    older = [p for p in points if p["ts"] <= cutoff]
    base, last = (older[-1] if older else points[0]), points[-1]
    pl_then, pl_now = base["market_value"] - base["invested"], last["market_value"] - last["invested"]
    return {
        "ccy": ccy, "since": base["ts"][:10], "full_week": bool(older),
        "value_then": base["market_value"], "value_now": last["market_value"],
        "result": pl_now - pl_then, "result_pct": (pl_now - pl_then) / base["market_value"] * 100 if base["market_value"] else None,
        "deposits": last["invested"] - base["invested"], "pl_total": pl_now,
    }


def holdings():
    """{ticker: nume} pentru pozitiile T212 si XTB."""
    from t212_api import load_cached_snapshot
    from xtb_positions import xtb_rows
    snap = load_cached_snapshot() or {}
    names = {i.get("ticker"): i.get("name") for i in (snap.get("instruments") or []) if isinstance(i, dict)}
    out = {}
    for p in snap.get("positions") or []:
        if p.get("ticker"):
            out[p["ticker"]] = names.get(p["ticker"]) or p["ticker"]
    for r in xtb_rows():
        if r.get("ticker"):
            out.setdefault(r["ticker"], r.get("name") or r["ticker"])
    return out


def week_changes(symbols):
    """Variatia pretului pe 7 zile calendaristice, pentru toate simbolurile intr-o singura cerere Yahoo."""
    import pandas as pd
    from yf_compat import yf
    if not symbols:
        return {}
    data = yf.download(sorted(set(symbols)), period="1mo", interval="1d", progress=False, group_by="ticker",
                       auto_adjust=False, threads=False)
    out = {}
    if data is None or data.empty:
        return out
    for symbol in set(symbols):
        try:
            frame = data[symbol] if isinstance(data.columns, pd.MultiIndex) else data
            close = frame["Close"].dropna()
            if len(close) < 2:
                continue
            base = close[close.index <= close.index[-1] - pd.Timedelta(days=7)]
            if base.empty or not float(base.iloc[-1]):
                continue
            out[symbol] = (float(close.iloc[-1]) / float(base.iloc[-1]) - 1) * 100
        except Exception:
            continue
    return out


def movers(held, changes_fn=None):
    from yahoo import resolve_yahoo_symbol
    changes_fn = changes_fn or week_changes
    symbols = {t: resolve_yahoo_symbol(t) for t in held}
    try:
        changes = changes_fn(list(symbols.values()))
    except Exception as e:
        print(f"[weekly] price changes failed: {e}", flush=True)
        changes = {}
    rows = sorted(((changes[s], t, held[t]) for t, s in symbols.items() if s in changes), reverse=True)
    up = [r for r in rows if r[0] > 0][:TOP]
    down = [r for r in reversed(rows) if r[0] < 0][:TOP]
    return up, down


def dividends_since_last(state):
    """Dividendele T212 incasate de la raportul trecut (din totalurile per ticker) si totalurile de acum."""
    from t212_api import load_cached_dividends
    totals = {t: float(v.get("total") or 0.0) for t, v in ((load_cached_dividends() or {}).get("dividends") or {}).items()}
    prev = state.get("div_totals")
    if not isinstance(prev, dict):
        return None, totals
    return sum(max(0.0, v - float(prev.get(t, 0.0))) for t, v in totals.items()), totals


def build(lang="RO", today=None, now=None, changes_fn=None, state=None):
    """Textul raportului: (subiect, corp, totalurile de dividende de salvat)."""
    import events
    from i18n import t
    today = today or date.today()
    state = _load_state() if state is None else state
    L = lambda key, **kw: t(key, _lang=lang, **kw)  # noqa: E731
    lines = [L("wr.mail_intro", a=(today - timedelta(days=7)).strftime("%d.%m.%Y"), b=today.strftime("%d.%m.%Y")), ""]

    v = value_summary(now)
    if v:
        c = v["ccy"]
        if not v["full_week"]:
            lines.append(L("wr.partial", d=v["since"]))
        lines.append(L("wr.value", now=f"{v['value_now']:,.2f} {c}", then=f"{v['value_then']:,.2f} {c}"))
        pct = f" ({v['result_pct']:+.2f}%)" if v["result_pct"] is not None else ""
        lines.append(L("wr.result", v=f"{v['result']:+,.2f} {c}{pct}"))
        if abs(v["deposits"]) >= 0.005:
            lines.append(L("wr.deposits", v=f"{v['deposits']:+,.2f} {c}"))
        lines.append(L("wr.pl_total", v=f"{v['pl_total']:+,.2f} {c}"))
    else:
        lines.append(L("wr.no_history"))

    held = holdings()
    up, down = movers(held, changes_fn) if held else ([], [])
    for title, rows in (("wr.up", up), ("wr.down", down)):
        if rows:
            lines += ["", L(title)]
            lines += ["  %-10s %+7.2f%%  %s" % (tk, pct, name) for pct, tk, name in rows]

    received, totals = dividends_since_last(state)
    if received:
        lines += ["", L("wr.dividends", v=f"{received:,.2f}")]

    evs = events.upcoming(events.load_cache(), list(held), today, days=7)
    lines += ["", L("wr.events") if evs else L("wr.no_events")]
    for ev in evs:
        when = ev["date"] + (" - " + ev["date_end"] if ev.get("date_end") else "")
        lines.append("  %s  %-10s %s" % (when, ev["ticker"], t("ev.type." + ev["type"], _lang=lang)))

    subject = L("wr.mail_subject", d=today.strftime("%d.%m.%Y"))
    return subject, "\n".join(lines), totals


def due(prefs, now, state):
    return (prefs["enabled"] and now.weekday() == prefs["weekday"] and now.hour >= prefs["hour"]
            and state.get("last_week") != week_key(now.date()))


def send(user, now=None, mark=True, changes_fn=None):
    """Construieste si trimite raportul la adresa utilizatorului; cu mark, saptamana e trecuta ca trimisa."""
    import notify
    import users
    from events import _user_lang
    email = users.email(user) if user else None
    if not email:
        return False
    now = now or datetime.now()
    state = _load_state()
    subject, body, totals = build(_user_lang(), now.date(), now, changes_fn, state)
    ok = notify.notify("weekly", subject, body, to=[email], sync=True,
                       key="weekly:%s:%s:%s" % (user, week_key(now.date()), "auto" if mark else time.time()), min_hours=0)
    if ok and mark:
        save_json_file(STATE_FILE, {"last_week": week_key(now.date()), "sent_at": now.isoformat(), "div_totals": totals})
    return ok


def maybe_send(user, now=None):
    now = now or datetime.now()
    if not due(load_prefs(), now, _load_state()):
        return False
    return send(user, now)
