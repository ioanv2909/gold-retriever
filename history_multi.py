import os
from datetime import datetime, timedelta

from core import load_json_file, update_json_file
from portfolio_model import fx
from t212_api import load_cached_snapshot
from xtb_positions import xtb_rows

from userctx import UPath
HISTORY_MULTI_FILE = UPath("portfolio_history_multi.json")
MIN_GAP_SECONDS = 14 * 60


def load_multi_history():
    return load_json_file(HISTORY_MULTI_FILE, [])


def record_multi_point(t212_account_currency=None, force=False):
    now = datetime.now()
    if not t212_account_currency:
        try:
            from core import load_config
            from t212_api import fetch_account_currency
            _cfg = load_config()
            t212_account_currency = fetch_account_currency(_cfg.get("api_key_id"), _cfg.get("api_secret"))[0]
        except Exception:
            t212_account_currency = None
    history = load_multi_history()
    if history and not force:
        try:
            last = datetime.fromisoformat(history[-1]["ts"])
            if (now - last).total_seconds() < MIN_GAP_SECONDS:
                return False
        except Exception:
            pass

    entries = {}
    snap = load_cached_snapshot() or {}
    cash = snap.get("cash") or {}
    inv = cash.get("invested") or 0.0
    ppl = cash.get("ppl") or 0.0
    if inv > 0 and inv + ppl > 0:
        entries["Trading 212"] = {"ccy": t212_account_currency or "EUR", "value": round(inv + ppl, 2), "cost": round(inv, 2)}

    sums = {}
    for r in xtb_rows():
        e = sums.setdefault(r["account"], {"ccy": r["account_currency"], "value": 0.0, "cost": 0.0})
        e["value"] += float(r["value_account"] or 0.0)
        e["cost"] += float(r["cost_account"] or 0.0)
    for label, e in sums.items():
        if e["value"] > 0:
            entries[label] = {"ccy": e["ccy"], "value": round(e["value"], 2), "cost": round(e["cost"], 2)}
    if not entries:
        return False

    _ccys = {e["ccy"] for e in entries.values() if e.get("ccy")} | {"EUR", "USD"}
    rates = {"EUR": 1.0}
    for _c in sorted(_ccys - {"EUR"}):
        rates[_c] = round(fx(_c, "EUR"), 6)
    point = {"ts": now.isoformat(timespec="seconds"), "entries": entries, "rates": rates}
    cutoff = (now - timedelta(days=30)).isoformat(timespec="seconds")

    def updater(h):
        h = list(h or []) + [point]
        recent = [p for p in h if p.get("ts", "") >= cutoff]
        old = {}
        for p in h:
            if p.get("ts", "") < cutoff:
                old[p["ts"][:10]] = p
        return list(old.values()) + recent

    update_json_file(HISTORY_MULTI_FILE, [], updater)
    return True


def _merged_history():
    real = load_multi_history()
    days = {}
    for mod in ("xtb_history_rebuild", "t212_history_rebuild"):
        try:
            m = __import__(mod)
            m.ensure_async()
            pts = m.load_points()
        except Exception:
            pts = []
        for p in pts:
            d = p["ts"][:10]
            if d in days:
                days[d]["entries"].update(p["entries"])
            else:
                days[d] = {"ts": p["ts"], "entries": dict(p["entries"]), "rates": dict(p["rates"])}
    first = real[0]["ts"][:10] if real else "9999-12-31"
    first_day, ccy_of = {}, {}
    for d in sorted(days):
        for label, e in days[d]["entries"].items():
            first_day.setdefault(label, d)
            ccy_of.setdefault(label, e["ccy"])
    out = []
    for d in sorted(days):
        if d >= first:
            continue
        pt = days[d]
        for label, fd in first_day.items():
            if fd > d and label not in pt["entries"]:
                pt["entries"][label] = {"ccy": ccy_of[label], "value": 0.0, "cost": 0.0}
        out.append(pt)
    return out + real


def _complete_rates(rates, needed):
    rates = dict(rates)
    pivot = next((k for k, v in rates.items() if v == 1.0), None)
    if pivot is None:
        return rates
    for c in needed:
        if c and c not in rates:
            try:
                rates[c] = fx(c, pivot)
            except Exception:
                pass
    return rates


def multi_history_records(portfolios, display_ccy):
    portfolios = list(portfolios or [])
    if not portfolios:
        return []
    out = []
    for p in _merged_history():
        entries = p.get("entries") or {}
        if any(x not in entries for x in portfolios):
            continue
        rates = _complete_rates(p.get("rates") or {}, {display_ccy} | {entries[x].get("ccy") for x in portfolios})
        if display_ccy not in rates:
            continue
        rd = rates[display_ccy] or 1.0
        val = cost = 0.0
        ok = True
        for label in portfolios:
            e = entries[label]
            rc = rates.get(e["ccy"])
            if rc is None:
                ok = False
                break
            val += e["value"] * rc / rd
            cost += e["cost"] * rc / rd
        if ok:
            out.append({"ts": p["ts"], "date": p["ts"][:10], "market_value": round(val, 2), "invested": round(cost, 2)})
    return out
