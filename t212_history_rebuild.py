"""Reconstruieste istoricul zilnic Trading 212 din ordinele executate + inchiderile zilnice Yahoo."""
import math
import os
import threading
import time
from collections import Counter

import pandas as pd

from core import load_config, load_json_file, update_json_file
from xtb_history_rebuild import _daily, _day, _fx_cache, _fx_series

from userctx import UPath
FILE = UPath("t212_history_reconstructed.json")
FILLS_FILE = UPath("t212_fills.json")
MAX_AGE_S = 24 * 3600
PAUSE = 11
MAX_PAGES = 150
_lock = threading.Lock()
_running = False


def _sync_fills():
    """Citeste ordinele executate (incremental) in data/t212_fills.json."""
    import requests
    from t212_api import BASE_URL, _headers, api_error

    cfg = load_config()
    kid, sec = cfg.get("api_key_id"), cfg.get("api_secret")
    if not kid or not sec:
        return None
    cache = load_json_file(FILLS_FILE, {})
    fills = list(cache.get("fills") or []) if isinstance(cache, dict) else []
    had_cache = bool(fills)
    known = {str(f["id"]) for f in fills}
    host = BASE_URL.split("/api/")[0]
    url, params, pages, retries = BASE_URL + "/equity/history/orders", {"limit": 50}, 0, 0
    complete = True
    while url and pages < MAX_PAGES:
        r = requests.get(url, headers=_headers(kid, sec), params=params, timeout=25)
        if r.status_code == 429 and retries < 4:
            retries += 1
            time.sleep(25)
            continue
        if r.status_code != 200:
            api_error(r, "/equity/history/orders", kid, sec)
            complete = False
            break
        retries = 0
        data = r.json()
        hit_known = False
        for it in data.get("items", []):
            o, f = it.get("order") or {}, it.get("fill")
            if not f or o.get("status") != "FILLED":
                continue
            fid = str(f.get("id"))
            if fid in known:
                hit_known = True
                continue
            wi = f.get("walletImpact") or {}
            qty = float(f.get("quantity") or 0)
            if o.get("side") == "SELL" and qty > 0:
                qty = -qty
            fills.append({
                "id": fid,
                "ticker": o.get("ticker"),
                "isin": (o.get("instrument") or {}).get("isin"),
                "ccy": (o.get("instrument") or {}).get("currency"),
                "time": f.get("filledAt"),
                "qty": qty,
                "price": float(f.get("price") or 0),
                "net": abs(float(wi.get("netValue") or 0)),
                "wccy": wi.get("currency"),
                "ftype": f.get("type"),
            })
            known.add(fid)
        pages += 1
        nxt = data.get("nextPagePath")
        if not nxt or (had_cache and hit_known):
            break
        url, params = host + nxt, {}
        time.sleep(PAUSE)
    if not fills:
        return None
    update_json_file(FILLS_FILE, {}, lambda _: {"updated": time.time(), "complete": complete, "fills": fills})
    return fills


def _symbol(ticker, isin):
    from yahoo import resolve_yahoo_symbol

    for args in ((ticker,), (ticker, isin)):
        try:
            s = resolve_yahoo_symbol(*args)
            if isinstance(s, (tuple, list)):
                s = s[0] if s else None
            if s:
                return s
        except Exception:
            continue
    return None


def _yahoo(sym, first_day, idx):
    import yfinance as yf

    tk = yf.Ticker(sym)
    hist = tk.history(start=(first_day - pd.Timedelta(days=10)).strftime("%Y-%m-%d"), auto_adjust=False)
    if hist is None or hist.empty:
        return None, []
    try:
        from price_clean import clean_history, is_fund

        cleaned = clean_history(hist, fund=is_fund(tk))
        hist = cleaned[0] if isinstance(cleaned, (tuple, list)) else cleaned
    except Exception:
        pass
    try:
        splits = [(_day(d), float(r)) for d, r in tk.splits.items() if r and float(r) > 0]
    except Exception:
        splits = []
    return _daily(hist["Close"], idx), splits


def _scale(close, day, price):
    try:
        c = float(close.loc[day])
    except Exception:
        return None
    if not c or c <= 0 or not price or price <= 0:
        return None
    best = min((1.0, 100.0, 0.01), key=lambda f: abs(math.log(price / (c * f))))
    return best if abs(math.log(price / (c * best))) < 0.35 else None


def rebuild():
    fills = _sync_fills()
    if not fills:
        return
    _fx_cache.clear()
    trade = [f for f in fills if f.get("ftype") in (None, "TRADE") and f.get("time") and f.get("ticker") and f.get("net")]
    notes = [f"{len(fills) - len(trade)} fill-uri ignorate (non-TRADE sau fara valoare)"]
    if not trade:
        return
    acct = Counter(f["wccy"] for f in trade if f.get("wccy")).most_common(1)[0][0]
    first = min(_day(f["time"]) for f in trade)
    end = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    idx = pd.date_range(first, end, freq="D")
    if len(idx) == 0:
        return

    by = {}
    for f in trade:
        by.setdefault(f["ticker"], []).append(f)
    value_tot = pd.Series(0.0, index=idx)
    cost_tot = pd.Series(0.0, index=idx)
    qty_end, skipped = {}, []

    for ticker, fl in by.items():
        fl.sort(key=lambda f: f["time"])
        sym = _symbol(ticker, fl[0].get("isin"))
        if not sym:
            skipped.append(f"{ticker}: fara simbol Yahoo")
            continue
        d0 = _day(fl[0]["time"])
        try:
            close, splits = _yahoo(sym, d0, idx)
        except Exception as e:
            skipped.append(f"{ticker}: eroare Yahoo {e}")
            continue
        if close is None or close.isna().all():
            skipped.append(f"{ticker}: fara preturi Yahoo")
            continue

        def factor(day):
            k = 1.0
            for sd, ratio in splits:
                if sd > day:
                    k *= ratio
            return k

        ccy = fl[0].get("ccy") or acct
        pence = ccy in ("GBX", "GBp")
        if pence:
            ccy = "GBP"
        last = fl[-1]
        lday = _day(last["time"])
        price = last["price"] / factor(lday)
        if pence:
            price /= 100.0
        scale = _scale(close, min(lday, idx[-1]), price)
        if scale is None:
            skipped.append(f"{ticker}: pret Yahoo incompatibil cu pretul din ordin")
            continue

        qty = pd.Series(0.0, index=idx)
        cost = pd.Series(0.0, index=idx)
        q_raw, c_cur, q_cur = 0.0, 0.0, 0.0
        for f in fl:
            day = _day(f["time"])
            k = factor(day)
            if f["qty"] > 0:
                q_raw += f["qty"]
                c_cur += f["net"]
            elif q_raw > 0:
                share = min(-f["qty"] / q_raw, 1.0)
                c_cur -= c_cur * share
                q_raw -= -f["qty"]
            q_cur += f["qty"] * k
            if abs(q_raw) < 1e-8:
                q_raw, c_cur = 0.0, 0.0
            if abs(q_cur) < 1e-8:
                q_cur = 0.0
            m = idx >= day
            qty[m] = q_cur
            cost[m] = c_cur
        qty_end[ticker] = q_cur
        value = (qty * close * scale * _fx_series(ccy, acct, idx)).fillna(0.0)
        value_tot = value_tot + value
        cost_tot = cost_tot + cost

    eur = _fx_series("EUR", "RON", idx)
    usd = _fx_series("USD", "RON", idx)
    points = []
    for d in idx:
        v, c_ = float(value_tot[d]), float(cost_tot[d])
        if v > 0 and c_ > 0:
            points.append({
                "ts": d.strftime("%Y-%m-%dT23:00:00"),
                "entries": {"Trading 212": {"ccy": acct, "value": round(v, 2), "cost": round(c_, 2)}},
                "rates": {"RON": 1.0, "EUR": round(float(eur[d]), 4), "USD": round(float(usd[d]), 4)},
            })
    out = {"updated": time.time(), "skipped": skipped, "notes": notes, "qty_end": qty_end, "points": points}
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
    """Reconstructie in fundal, cel mult o data la 24h."""
    global _running
    data = load_json_file(FILE, {})
    if isinstance(data, dict) and time.time() - data.get("updated", 0) < MAX_AGE_S:
        return
    with _lock:
        if _running:
            return
        _running = True
    threading.Thread(target=_run, daemon=True).start()


def load_points():
    data = load_json_file(FILE, {})
    return (data.get("points") or []) if isinstance(data, dict) else []
