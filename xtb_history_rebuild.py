"""Reconstruieste istoricul zilnic al portofoliilor XTB din achizitii + inchiderile zilnice Yahoo."""
import math
import os
import threading
import time

import pandas as pd

from core import load_json_file, update_json_file
from xtb import load_xtb

from userctx import UPath
FILE = UPath("xtb_history_reconstructed.json")
MAX_AGE_S = 24 * 3600
_lock = threading.Lock()
_running = False
_fx_cache = {}


def _sig():
    accounts = load_xtb().get("accounts") or {}
    return f"{len(accounts)}|" + "|".join(sorted(str(a.get("report_time")) for a in accounts.values()))


def _day(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.normalize()


def _daily(series, idx):
    s = series.copy()
    s.index = pd.DatetimeIndex(s.index)
    if s.index.tz is not None:
        s.index = s.index.tz_localize(None)
    s.index = s.index.normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx.union(s.index)).ffill().bfill().reindex(idx)


def _start(idx):
    return (idx[0] - pd.Timedelta(days=10)).strftime("%Y-%m-%d")


def _yahoo_close(sym, idx):
    import yfinance as yf

    if isinstance(sym, (tuple, list)):
        sym = sym[0]
    tk = yf.Ticker(sym)
    hist = tk.history(start=_start(idx))
    if hist is None or hist.empty:
        return None
    try:
        from price_clean import clean_history, is_fund

        cleaned = clean_history(hist, fund=is_fund(tk))
        hist = cleaned[0] if isinstance(cleaned, (tuple, list)) else cleaned
    except Exception:
        pass
    return _daily(hist["Close"], idx)


def _fx_series(c, a, idx):
    if c == a:
        return pd.Series(1.0, index=idx)
    key = (c, a, idx[0])
    if key not in _fx_cache:
        s = None
        try:
            import yfinance as yf

            h = yf.Ticker(f"{c}{a}=X").history(start=_start(idx))
            if h is not None and not h.empty:
                s = _daily(h["Close"], idx)
        except Exception:
            s = None
        if s is None or s.isna().all():
            from portfolio_model import fx

            s = pd.Series(float(fx(c, a)), index=idx)
        _fx_cache[key] = s
    return _fx_cache[key]


def _scale(close, current):
    vals = close.dropna()
    if vals.empty or not current:
        return None
    last = float(vals.iloc[-1])
    if last <= 0 or float(current) <= 0:
        return None
    best = min((1.0, 100.0, 0.01), key=lambda f: abs(math.log(float(current) / (last * f))))
    return best if abs(math.log(float(current) / (last * best))) < 0.25 else None


def rebuild():
    from xtb_positions import _account_position_group, _purchase_events, xtb_rows

    _fx_cache.clear()
    data = load_xtb()
    accounts = data.get("accounts") or {}
    items, skipped, first = [], [], None
    for r in xtb_rows():
        key = r["account_key"]
        group = _account_position_group(accounts.get(key) or {}, r["ticker"])
        ops = (data.get("cash_ops") or {}).get(key) or {}
        buys = []
        for p in _purchase_events(ops, r["ticker"], group):
            vol, amt = float(p.get("volume") or 0), float(p.get("amount") or 0)
            if p.get("time") and vol > 0 and amt < 0:
                buys.append((_day(p["time"]), vol, -amt))
        if not buys or not r.get("yahoo_symbol"):
            skipped.append(f"{r['ticker']}: fara achizitii sau simbol Yahoo")
            continue
        d0 = min(b[0] for b in buys)
        first = d0 if first is None else min(first, d0)
        items.append((r, buys))
    if not items:
        return
    end = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    idx = pd.date_range(first, end, freq="D")
    if len(idx) == 0:
        return

    per_account = {}
    for r, buys in items:
        try:
            close = _yahoo_close(r["yahoo_symbol"], idx)
        except Exception as e:
            skipped.append(f"{r['ticker']}: eroare Yahoo {e}")
            continue
        if close is None or close.isna().all():
            skipped.append(f"{r['ticker']}: fara preturi Yahoo")
            continue
        scale = _scale(close, r.get("currentPrice"))
        if scale is None:
            skipped.append(f"{r['ticker']}: pret Yahoo incompatibil cu pretul curent")
            continue
        a = r["account_currency"]
        c = r.get("currencyCode") or a
        if c in ("GBX", "GBp"):
            c = "GBP"
        qty = pd.Series(0.0, index=idx)
        cost = pd.Series(0.0, index=idx)
        for day, vol, amt in buys:
            m = idx >= day
            qty[m] += vol
            cost[m] += amt
        value = (qty * close * scale * _fx_series(c, a, idx)).fillna(0.0)
        acc = per_account.setdefault(r["account"], {"ccy": a, "value": pd.Series(0.0, index=idx), "cost": pd.Series(0.0, index=idx)})
        acc["value"] = acc["value"] + value
        acc["cost"] = acc["cost"] + cost

    eur = _fx_series("EUR", "RON", idx)
    usd = _fx_series("USD", "RON", idx)
    points = []
    for d in idx:
        entries = {}
        for label, acc in per_account.items():
            v, c_ = float(acc["value"][d]), float(acc["cost"][d])
            if v > 0 and c_ > 0:
                entries[label] = {"ccy": acc["ccy"], "value": round(v, 2), "cost": round(c_, 2)}
        if entries:
            points.append({
                "ts": d.strftime("%Y-%m-%dT23:00:00"),
                "entries": entries,
                "rates": {"RON": 1.0, "EUR": round(float(eur[d]), 4), "USD": round(float(usd[d]), 4)},
            })
    out = {"updated": time.time(), "sig": _sig(), "skipped": skipped, "points": points}
    update_json_file(FILE, {}, lambda _: out)


def _run():
    global _running
    try:
        rebuild()
    except Exception:
        pass
    finally:
        with _lock:
            _running = False


def ensure_async():
    """Porneste reconstructia in fundal daca lipseste, e veche (24h) sau s-au importat fisiere noi."""
    global _running
    data = load_json_file(FILE, {})
    if isinstance(data, dict) and data.get("sig") == _sig() and time.time() - data.get("updated", 0) < MAX_AGE_S:
        return
    with _lock:
        if _running:
            return
        _running = True
    threading.Thread(target=_run, daemon=True).start()


def load_points():
    data = load_json_file(FILE, {})
    return (data.get("points") or []) if isinstance(data, dict) else []
