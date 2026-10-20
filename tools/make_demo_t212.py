#!/usr/bin/env python3
"""Write a fictional Trading 212 snapshot into the 'demo' user's data.

Real US tickers and real Yahoo prices, invented purchases. No API keys needed.
Run after make_demo.py, inside the container:
    docker compose exec gold-retriever python tools/make_demo_t212.py
"""
import json
import math
import os
import sys
import time
from bisect import bisect_left
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import userctx  # noqa: E402
import users  # noqa: E402

USER = "demo"
BUDGET_USD = 160.0   # invented monthly purchase per stock
MONTHS_BACK = 14
STOCKS = [
    # t212 ticker, yahoo, name, isin, dividend per share per quarter (USD)
    ("AMZN_US_EQ", "AMZN", "Amazon.com", "US0231351067", 0.0),
    ("GOOGL_US_EQ", "GOOGL", "Alphabet (Class A)", "US02079K3059", 0.0),
    ("V_US_EQ", "V", "Visa", "US92826C8394", 0.52),
    ("JNJ_US_EQ", "JNJ", "Johnson & Johnson", "US4781601046", 1.24),
    ("PG_US_EQ", "PG", "Procter & Gamble", "US7427181091", 1.06),
    ("TSLA_US_EQ", "TSLA", "Tesla", "US88160R1014", 0.0),
]
FREE_CASH = 312.45
REALIZED = 118.30


def floor4(x):
    return math.floor(x * 1e4) / 1e4


def series(sym):
    from yf_compat import yf
    s = yf.Ticker(sym).history(period="2y", auto_adjust=False)["Close"].dropna()
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


def dump(path, data):
    with open(os.fspath(path), "w") as f:
        json.dump(data, f)


def main():
    if not users.exists(USER):
        sys.exit("Run tools/make_demo.py first (user '%s' does not exist)." % USER)
    userctx.set_user(USER)
    os.makedirs(str(userctx.user_dir()), exist_ok=True)

    from core import (ACCOUNT_INFO_CACHE_FILE, DIVIDENDS_CACHE_FILE,
                      PORTFOLIO_CACHE_FILE)

    today = date.today()
    fx = series("EURUSD=X")
    if not fx:
        sys.exit("Cannot fetch EURUSD=X. Is the container online?")
    rate = fx[-1][1]  # USD per 1 EUR

    positions, instruments, dividends = [], [], {}
    invested = ppl = 0.0
    months = month_starts(today)

    for t212, sym, name, isin, dps in STOCKS:
        ser = series(sym)
        if not ser:
            sys.exit("No price history for %s." % sym)
        dates = [d for d, _ in ser]
        buys = []
        for m in months:
            j = bisect_left(dates, m)
            if j >= len(ser) or ser[j][0] > today:
                continue
            d, p = ser[j]
            buys.append((d, p, floor4(BUDGET_USD / p)))
        qty = floor4(sum(b[2] for b in buys))
        cost = sum(b[1] * b[2] for b in buys)
        avg, cur = round(cost / qty, 4), round(ser[-1][1], 4)
        p_eur = round((cur - avg) * qty / rate, 2)
        invested += qty * avg / rate
        ppl += p_eur
        first = datetime.combine(buys[0][0], datetime.min.time()).replace(hour=10, minute=12)
        positions.append({
            "ticker": t212, "quantity": qty, "averagePrice": avg, "currentPrice": cur,
            "ppl": p_eur, "fxPpl": 0.0,
            "initialFillDate": first.strftime("%Y-%m-%dT%H:%M:%S.000+02:00"),
            "frontend": "API", "maxBuy": 10000.0, "maxSell": None, "pieQuantity": 0,
        })
        instruments.append({
            "ticker": t212, "type": "STOCK", "workingScheduleId": 1, "isin": isin,
            "currencyCode": "USD", "name": name, "shortName": sym,
            "maxOpenQuantity": 100000.0, "extendedHours": True, "addedOn": "2018-07-12T00:00:00.000+03:00",
        })
        if dps:
            paid = [m.replace(day=15) for m in months if m.month in (3, 6, 9, 12) and m.replace(day=15) <= today]
            total, last = 0.0, None
            for dd in paid:
                held = sum(b[2] for b in buys if b[0] < dd)
                if held > 0:
                    total += held * dps * 0.85 / rate
                    last = dd
            if last:
                dividends[t212] = {"total": round(total, 2), "count": len([x for x in paid if sum(b[2] for b in buys if b[0] < x) > 0]),
                                   "last_paid_on": last.isoformat() + "T00:00:00.000+03:00"}

    invested, ppl = round(invested, 2), round(ppl, 2)
    now = time.time()
    dump(PORTFOLIO_CACHE_FILE, {
        "fetched_at": now,
        "cash": {"free": FREE_CASH, "total": round(FREE_CASH + invested + ppl, 2), "ppl": ppl,
                 "result": REALIZED, "invested": invested, "pieCash": 0.0, "blocked": 0},
        "positions": positions, "instruments": instruments,
        "errors": {"cash": None, "portfolio": None, "instruments": None}, "stale_errors": {},
    })
    dump(ACCOUNT_INFO_CACHE_FILE, {"fetched_at": now, "currencyCode": "EUR"})
    dump(DIVIDENDS_CACHE_FILE, {"fetched_at": now, "dividends": dividends, "error": None})

    print("T212 demo snapshot written: %d positions, invested %.2f EUR, P/L %.2f EUR, EURUSD %.4f"
          % (len(positions), invested, ppl, rate))
    print("Reload the app as '%s'." % USER)


if __name__ == "__main__":
    main()
