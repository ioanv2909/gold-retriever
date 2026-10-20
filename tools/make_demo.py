#!/usr/bin/env python3
"""Create a fictional 'demo' user with a synthetic XTB portfolio.

Real tickers and real historical prices (Yahoo), invented deposits/purchases.
Run inside the container, from /app:
    docker compose exec gold-retriever python tools/make_demo.py
"""
import argparse
import hashlib
import json
import math
import os
import sys
from bisect import bisect_left
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import userctx  # noqa: E402
import users  # noqa: E402

ACCOUNTS = [
    {
        "ccy": "EUR", "seed": "demo-eur", "first_deposit": 5000, "deposit": 1000,
        "instruments": [
            {"t": "VWCE.DE", "name": "Vanguard FTSE All-World UCITS ETF (USD) Acc", "cat": "ETF", "isin": "IE00BK5BQT80", "w": 0.55},
            {"t": "SXR8.DE", "name": "iShares Core S&P 500 UCITS ETF (Acc)", "cat": "ETF", "isin": "IE00B5BMR087", "w": 0.30},
            {"t": "EUNL.DE", "name": "iShares Core MSCI World UCITS ETF (Acc)", "cat": "ETF", "isin": "IE00B4L5Y983", "w": 0.15},
        ],
    },
    {
        "ccy": "USD", "seed": "demo-usd", "first_deposit": 3000, "deposit": 600,
        "instruments": [
            {"t": "AAPL.US", "name": "Apple", "cat": "STOCK", "isin": "US0378331005", "w": 0.30, "dps": 0.25},
            {"t": "MSFT.US", "name": "Microsoft", "cat": "STOCK", "isin": "US5949181045", "w": 0.30, "dps": 0.83},
            {"t": "NVDA.US", "name": "NVIDIA", "cat": "STOCK", "isin": "US67066G1040", "w": 0.20, "dps": 0.0},
            {"t": "KO.US", "name": "Coca-Cola", "cat": "STOCK", "isin": "US1912161007", "w": 0.20, "dps": 0.51},
        ],
    },
]
WATCHLIST = [("GOOGL", "Alphabet"), ("TSLA", "Tesla"), ("V", "Visa")]
MONTHS_BACK = 21


def floor4(x):
    return math.floor(x * 1e4) / 1e4


def fetch_series(sym):
    from yf_compat import yf
    h = yf.Ticker(sym).history(period="2y", auto_adjust=False)
    s = h["Close"].dropna()
    idx = s.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    return sorted((d.date(), float(p)) for d, p in zip(idx, s.values))


def month_starts(today):
    dt = date(today.year, today.month, 1)
    for _ in range(MONTHS_BACK):
        dt = (dt - timedelta(days=1)).replace(day=1)
    out = []
    while dt <= today:
        out.append(dt)
        dt = (dt.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def build_account(acc, series, today, counter):
    ccy = acc["ccy"]
    ops, lots = [], {i["t"]: [] for i in acc["instruments"]}

    def nid():
        counter[0] += 1
        return "9%07d" % counter[0]

    for k, m in enumerate(month_starts(today)):
        dep = acc["first_deposit"] if k == 0 else acc["deposit"]
        ops.append({"type": "Deposit", "instrument": None, "ticker": None, "category": None,
                    "time": m.isoformat() + "T09:00:00", "amount": float(dep), "id": nid(),
                    "comment": "Demo deposit", "position_id": None})
        for ins in acc["instruments"]:
            ser = series[ins["t"]]
            j = bisect_left([d for d, _ in ser], m)
            if j >= len(ser):
                continue
            d, p = ser[j]
            if d > today:
                continue
            vol = floor4(dep * ins["w"] / p)
            if vol <= 0:
                continue
            cost = round(vol * p, 2)
            pid = nid()
            ts = d.isoformat() + "T10:00:00"
            ops.append({"type": "Stock purchase", "instrument": ins["name"], "ticker": ins["t"],
                        "category": ins["cat"], "time": ts, "amount": -cost, "id": nid(),
                        "comment": "OPEN BUY %s 1/1 @ %.2f" % (ins["t"], p), "position_id": pid,
                        "stock_purchase": {"ticker": ins["t"], "part": 1, "total": 1, "price": round(p, 2)},
                        "isin": ins["isin"]})
            lots[ins["t"]].append({"position_id": pid, "volume": vol, "open_price": round(p, 4),
                                   "open_time": ts, "date": d})

    for ins in acc["instruments"]:
        dps = ins.get("dps") or 0
        if not dps:
            continue
        for m in month_starts(today):
            if m.month not in (3, 6, 9, 12):
                continue
            dd = m.replace(day=15)
            if dd > today:
                continue
            held = sum(l["volume"] for l in lots[ins["t"]] if l["date"] < dd)
            if held <= 0:
                continue
            gross = round(held * dps, 2)
            ts = dd.isoformat() + "T12:00:00"
            for typ, amt, cmt in (("Dividend", gross, "%s USD %.2f/ SHR" % (ins["t"], dps)),
                                  ("Withholding tax", -round(gross * 0.15, 2), "%s USD WHT 15%%" % ins["t"])):
                ops.append({"type": typ, "instrument": ins["name"], "ticker": ins["t"],
                            "category": ins["cat"], "time": ts, "amount": amt, "id": nid(),
                            "comment": cmt, "position_id": None, "isin": ins["isin"]})

    positions, tot_val, tot_profit = [], 0.0, 0.0
    for ins in acc["instruments"]:
        ls = lots[ins["t"]]
        if not ls:
            continue
        last = series[ins["t"]][-1][1]
        vol = round(sum(l["volume"] for l in ls), 4)
        cost = sum(l["volume"] * l["open_price"] for l in ls)
        value = round(vol * last, 2)
        profit = round(value - cost, 2)
        positions.append({
            "instrument": ins["name"], "ticker": ins["t"], "category": ins["cat"],
            "volume": vol, "value": value, "open_price": round(cost / vol, 4),
            "net_profit": profit, "net_profit_pct": round(profit / cost * 100, 2),
            "lots": [{"position_id": l["position_id"], "volume": l["volume"],
                      "value": round(l["volume"] * last, 2), "current_price": round(last, 4),
                      "open_price": l["open_price"], "open_time": l["open_time"]} for l in ls],
            "initial_fill": min(l["open_time"] for l in ls), "isin": ins["isin"],
        })
        tot_val += value
        tot_profit += profit

    cash_sum = round(sum(o["amount"] for o in ops), 2)
    tot_val, tot_profit = round(tot_val, 2), round(tot_profit, 2)
    key = "%s-%s" % (ccy, hashlib.sha256(acc["seed"].encode()).hexdigest()[:6])
    return {
        "account_key": key, "currency": ccy,
        "report_time": datetime.now().isoformat(timespec="seconds"),
        "summary": {"value": tot_val, "profit": tot_profit},
        "positions": positions, "cash_ops": ops, "total_row": cash_sum, "closed": [],
        "checks": {"cash_sum": cash_sum, "total_row": cash_sum,
                   "positions_value_sum": tot_val, "summary_value": tot_val},
        "unknown_types": [],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="demo")
    ap.add_argument("--password", default="demo")
    a = ap.parse_args()

    if not users.has_users():
        sys.exit("No users.json yet: create the admin account first, then run this script.")
    if users.exists(a.user):
        users.set_password(a.user, a.password)
        print("User '%s' exists: password reset, data will be merged/overwritten." % a.user)
    else:
        users.create_user(a.user, a.password, "user")
        print("User '%s' created." % a.user)

    userctx.set_user(a.user)
    os.makedirs(str(userctx.user_dir()), exist_ok=True)

    import xtb
    from core import WATCHLIST_FILE
    from yahoo import resolve_yahoo_symbol

    today = date.today()
    series = {}
    for acc in ACCOUNTS:
        for ins in acc["instruments"]:
            sym = resolve_yahoo_symbol(ins["t"])
            if not sym:
                sys.exit("Cannot resolve Yahoo symbol for %s" % ins["t"])
            ser = fetch_series(sym)
            if not ser:
                sys.exit("No price history for %s (%s). Is the container online?" % (ins["t"], sym))
            series[ins["t"]] = ser
            print("  %-8s -> %-8s %d days" % (ins["t"], sym, len(ser)))

    counter = [0]
    for acc in ACCOUNTS:
        parsed = build_account(acc, series, today, counter)
        rep = xtb.import_xtb(parsed, "demo-%s-%s" % (acc["seed"], datetime.now().strftime("%Y%m%d%H%M%S")))
        print(acc["ccy"], "account:", len(parsed["positions"]), "positions,",
              len(parsed["cash_ops"]), "cash ops, value", parsed["summary"]["value"])

    wl = [{"symbol": s, "name": n, "added": (today - timedelta(days=30)).isoformat()} for s, n in WATCHLIST]
    with open(os.fspath(WATCHLIST_FILE), "w") as f:
        json.dump(wl, f)

    print("\nDone. Log in as '%s' / '%s' and wait 1-2 minutes for prices and history." % (a.user, a.password))


if __name__ == "__main__":
    main()
