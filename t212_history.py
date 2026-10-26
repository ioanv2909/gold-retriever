"""Istoricul contului Trading 212: prima depunere, totaluri si randament XIRR."""
import json
import sys
import time
from datetime import datetime, timezone

PAUSE = 11
MAX_PAGES = 80


def parse(iso):
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def xirr(flows):
    flows = [(d, a) for d, a in flows if a]
    if len(flows) < 2:
        return None
    t0 = min(d for d, _ in flows)

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).total_seconds() / 86400 / 365.25) for d, a in flows)

    lo, hi = -0.95, 20.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def fetch_pages(kid, sec, path, label):
    import requests
    from t212_api import BASE_URL, _headers, api_error

    host = BASE_URL.split("/api/")[0]
    url, params, items, n, retries = BASE_URL + path, {"limit": 50}, [], 0, 0
    while url and n < MAX_PAGES:
        r = requests.get(url, headers=_headers(kid, sec), params=params, timeout=25)
        if r.status_code == 429 and retries < 4:
            retries += 1
            time.sleep(25)
            continue
        if r.status_code != 200:
            print("  " + api_error(r, path, kid, sec))
            return items, False
        retries = 0
        data = r.json()
        items += data.get("items", [])
        print(f"  {label}: {len(items)}", flush=True)
        nxt = data.get("nextPagePath")
        if nxt:
            url = host + nxt if nxt.startswith("/api") else BASE_URL + nxt
        else:
            url = None
        params = {}
        n += 1
        if url:
            time.sleep(PAUSE)
    return items, True


def order_date(o):
    fill, od = o.get("fill") or {}, o.get("order") or {}
    return o.get("dateExecuted") or fill.get("filledAt") or od.get("createdAt") or o.get("dateCreated")


def main():
    from core import load_config
    from t212_api import load_cached_snapshot

    cfg = load_config()
    kid, sec = cfg.get("api_key_id"), cfg.get("api_secret")
    if not kid or not sec:
        print("Lipsesc cheile API din configurare.")
        return
    out = {}

    print("Citesc depunerile si retragerile...")
    tx, ok = fetch_pages(kid, sec, "/equity/history/transactions", "tranzactii")
    deposits = sorted((parse(t["dateTime"]), abs(float(t.get("amount") or 0))) for t in tx if t.get("type") == "DEPOSIT" and t.get("dateTime"))
    withdrawals = sorted((parse(t["dateTime"]), abs(float(t.get("amount") or 0))) for t in tx if t.get("type") == "WITHDRAW" and t.get("dateTime"))
    if not deposits:
        types = sorted({str(t.get("type")) for t in tx})
        print("Nu am gasit depuneri. Tipurile intalnite:", types, "| complet:", ok)
    else:
        dsum = sum(a for _, a in deposits)
        wsum = sum(a for _, a in withdrawals)
        print(f"prima depunere: {deposits[0][0]:%d.%m.%Y} | depuneri: {len(deposits)} | total depus: {dsum:,.2f} | retrageri: {wsum:,.2f}")
        by_year = {}
        for d, a in deposits:
            by_year[d.year] = by_year.get(d.year, 0.0) + a
        print("depus pe ani:", {y: round(v, 2) for y, v in sorted(by_year.items())})

        snap = load_cached_snapshot() or {}
        cash = snap.get("cash") or {}
        total = cash.get("total")
        if total is None:
            total = (cash.get("free") or 0) + (cash.get("invested") or 0) + (cash.get("ppl") or 0) + (cash.get("pieCash") or 0)
        now = datetime.now(timezone.utc)
        net = total + wsum - dsum
        print(f"valoarea contului acum: {total:,.2f} | castig net (valoare + retrageri - depuneri): {net:+,.2f} = {net / dsum * 100:+.1f}% din depuneri")
        flows = [(d, -a) for d, a in deposits] + [(d, a) for d, a in withdrawals] + [(now, total)]
        r = xirr(flows)
        if r is None:
            print("Nu am putut calcula randamentul anualizat (XIRR).")
        else:
            print(f"randament anualizat ponderat cu fluxurile (XIRR): {r * 100:+.1f}%/an")
        out.update({"first_deposit": deposits[0][0].isoformat(), "deposits_total": round(dsum, 2), "withdrawals_total": round(wsum, 2),
                    "account_value": round(total, 2), "net_gain": round(net, 2), "xirr": None if r is None else round(r, 4)})

    if "--orders" in sys.argv:
        print("Citesc ordinele (poate dura cateva minute)...")
        orders, ok = fetch_pages(kid, sec, "/equity/history/orders", "ordine")
        dates = sorted(d for d in (order_date(o) for o in orders) if d)
        if dates:
            print(f"primul ordin: {parse(dates[0]):%d.%m.%Y} | ultimul: {parse(dates[-1]):%d.%m.%Y} | total ordine: {len(orders)} | complet: {ok}")
            out.update({"first_order": dates[0], "last_order": dates[-1], "orders": len(orders)})
        else:
            print("Nu am gasit date in ordine.")

    try:
        json.dump(out, open("data/t212_first_dates.json", "w"), indent=2)
        print("salvat in data/t212_first_dates.json")
    except Exception as e:
        print("nu am putut salva rezultatul:", e)


if __name__ == "__main__":
    main()

