#!/usr/bin/env python3
"""Write synthetic Trading 212 history/flows for the 'demo' user.

Reuses the invented purchases of make_demo_t212.py. Run after it:
    docker compose exec gold-retriever python tools/make_demo_history.py
"""
import json
import os
import sys
import time
from bisect import bisect_right
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import userctx  # noqa: E402
import users  # noqa: E402
import make_demo_t212 as m  # noqa: E402


def last_le(ser, d):
    """Close at or before date d (ser: sorted [(date, price)])."""
    i = bisect_right([x for x, _ in ser], d) - 1
    return ser[i][1] if i >= 0 else None


def xirr(flows, end_value, end_date):
    """flows: [(date, amount)] deposits positive. Returns annual rate as fraction."""
    items = [(d, -a) for d, a in flows] + [(end_date, end_value)]
    t0 = items[0][0]

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.0) for d, a in items)

    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def main():
    if not users.exists(m.USER):
        sys.exit("Run make_demo.py and make_demo_t212.py first.")
    userctx.set_user(m.USER)
    os.makedirs(str(userctx.user_dir()), exist_ok=True)

    today = date.today()
    months = m.month_starts(today)
    eurusd = m.series("EURUSD=X")
    try:
        eurron = m.series("EURRON=X")
    except Exception:
        eurron = []
    if not eurusd:
        sys.exit("Cannot fetch EURUSD=X.")

    stock_ser, buys = {}, {}
    for t212, sym, name, isin, dps in m.STOCKS:
        ser = m.series(sym)
        stock_ser[t212] = ser
        dates = [d for d, _ in ser]
        lst = []
        for mo in months:
            from bisect import bisect_left
            j = bisect_left(dates, mo)
            if j >= len(ser) or ser[j][0] > today:
                continue
            d, p = ser[j]
            lst.append((d, p, m.floor4(m.BUDGET_USD / p)))
        buys[t212] = lst

    first_day = min(b[0] for lst in buys.values() for b in lst)
    days = [d for d, _ in eurusd if first_day <= d <= today]

    points = []
    for d in days:
        fx = last_le(eurusd, d)
        value = cost = 0.0
        for t212, lst in buys.items():
            held = [b for b in lst if b[0] <= d]
            if not held:
                continue
            q = sum(b[2] for b in held)
            px = last_le(stock_ser[t212], d)
            if px is None:
                continue
            value += q * px / fx
            cost += sum(b[1] * b[2] / (last_le(eurusd, b[0]) or fx) for b in held)
        ron = last_le(eurron, d) if eurron else None
        points.append({
            "ts": d.isoformat() + "T22:00:00",
            "entries": {"Trading 212": {"ccy": "EUR", "value": round(value, 2), "cost": round(cost, 2)}},
            "rates": {"RON": round(ron or 5.0, 4), "EUR": 1.0, "USD": round(fx, 4)},
        })

    qty_end = {t: round(sum(b[2] for b in lst), 4) for t, lst in buys.items()}
    with open(os.fspath(userctx.UPath("t212_history_reconstructed.json")), "w") as f:
        json.dump({"updated": time.time(), "skipped": [], "notes": ["demo data"],
                   "qty_end": qty_end, "points": points}, f)

    # deposits: one per month = what the invented purchases cost, first one + free cash
    flows = []
    for k, mo in enumerate(months):
        spent = sum(b[1] * b[2] / (last_le(eurusd, b[0]) or 1.0)
                    for lst in buys.values() for b in lst if b[0].year == mo.year and b[0].month == mo.month)
        if k == 0:
            spent += m.FREE_CASH
        if spent > 0:
            flows.append((mo, round(spent, 2)))
    with open(os.fspath(userctx.UPath("t212_flows.json")), "w") as f:
        json.dump({"updated": time.time(),
                   "flows": [{"t": d.isoformat() + "T09:00:00", "type": "DEPOSIT", "amount": a} for d, a in flows]}, f)

    with open(os.fspath(userctx.UPath("portfolio_cache.json"))) as f:
        total = json.load(f)["cash"]["total"]
    dep_total = round(sum(a for _, a in flows), 2)
    with open(os.fspath(userctx.UPath("t212_first_dates.json")), "w") as f:
        json.dump({"first_deposit": flows[0][0].isoformat() + "T09:00:00", "deposits_total": dep_total,
                   "withdrawals_total": 0.0, "account_value": total,
                   "net_gain": round(total - dep_total, 2),
                   "xirr": round(xirr(flows, total, today), 4)}, f)

    print("History: %d daily points, %d deposits totalling %.2f EUR, account value %.2f EUR."
          % (len(points), len(flows), dep_total, total))


if __name__ == "__main__":
    main()
