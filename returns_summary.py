"""Randament pe perioada de referinta: T212 (XIRR din depuneri), XTB si total (estimari)."""
import json
import os
import threading
import time
from datetime import datetime, timezone

import streamlit as st

from i18n import t

from userctx import UPath
FLOWS_FILE = UPath("t212_flows.json")
MAX_AGE_S = 24 * 3600
PAUSE = 11
MAX_PAGES = 80
MIN_REAL_DEPOSIT = 1000.0
FLOOR = datetime(2024, 3, 28, tzinfo=timezone.utc)
_lock = threading.Lock()
_running = False


def _parse(iso):
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _age(iso, now):
    return max((now - max(_parse(iso), FLOOR)).days, 1) / 365.25


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


def _fetch_transactions(kid, sec):
    import requests
    from t212_api import BASE_URL, _headers

    host = BASE_URL.split("/api/")[0]
    url, params, items, n, retries = BASE_URL + "/equity/history/transactions", {"limit": 50}, [], 0, 0
    while url and n < MAX_PAGES:
        r = requests.get(url, headers=_headers(kid, sec), params=params, timeout=25)
        if r.status_code == 429 and retries < 4:
            retries += 1
            time.sleep(25)
            continue
        if r.status_code != 200:
            return items, False
        retries = 0
        data = r.json()
        items += data.get("items", [])
        nxt = data.get("nextPagePath")
        url = (host + nxt if nxt.startswith("/api") else BASE_URL + nxt) if nxt else None
        params = {}
        n += 1
        if url:
            time.sleep(PAUSE)
    return items, True


def _refresh_flows():
    global _running
    try:
        from core import load_config

        cfg = load_config()
        kid, sec = cfg.get("api_key_id"), cfg.get("api_secret")
        if not kid or not sec:
            return
        tx, ok = _fetch_transactions(kid, sec)
        if not ok or not tx:
            return
        flows = [{"t": t["dateTime"], "type": t["type"], "amount": abs(float(t.get("amount") or 0))}
                 for t in tx if t.get("type") in ("DEPOSIT", "WITHDRAW") and t.get("dateTime")]
        os.makedirs(os.path.dirname(FLOWS_FILE), exist_ok=True)
        tmp = FLOWS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"updated": time.time(), "flows": flows}, f)
        os.replace(tmp, FLOWS_FILE)
    except Exception:
        pass
    finally:
        with _lock:
            _running = False


def _flows():
    """Fluxurile T212 din cache; porneste in fundal reimprospatarea cand lipsesc sau sunt vechi."""
    global _running
    data = None
    try:
        with open(FLOWS_FILE) as f:
            data = json.load(f)
    except Exception:
        pass
    stale = data is None or time.time() - data.get("updated", 0) > MAX_AGE_S
    if stale:
        with _lock:
            start = not _running
            _running = True
        if start:
            threading.Thread(target=_refresh_flows, daemon=True).start()
    return data


def _base_ccy():
    try:
        from core import load_config
        from t212_api import fetch_account_currency
        cfg = load_config()
        c = fetch_account_currency(cfg.get("api_key_id"), cfg.get("api_secret"))[0]
        if c and c != "?":
            return c
    except Exception:
        pass
    return "EUR"


def _estimate(name, rows, ccy=""):
    if not rows:
        return None
    cost = sum(c for c, _, _ in rows)
    pl = sum(p for _, p, _ in rows)
    wage = sum(c * a for c, _, a in rows) / cost
    r = pl / cost
    annual = (1 + r) ** (1 / wage) - 1 if wage >= 1 else None
    txt = t("ret.est", name=name, ccy=ccy, cost=f"{cost:,.0f}", pl=f"{pl:+,.0f}", r=f"{r * 100:+.1f}", wage=f"{wage:.2f}")
    txt += t("ret.annual_est", a=f"{annual * 100:+.1f}") if annual is not None else t("ret.under_year")
    return txt


def _xirr_line(name, flows, final_value, now, extra="", ccy=""):
    real = [d for d, a in flows if a < 0 and abs(a) >= MIN_REAL_DEPOSIT]
    if not real:
        return None
    start = min(real)
    years = (now - start).days / 365.25
    invested = -sum(a for _, a in flows if a < 0)
    back = sum(a for _, a in flows if a > 0)
    net = final_value + back - invested
    txt = t("ret.xirr_line", name=name, ccy=ccy, inv=f"{invested:,.0f}", val=f"{final_value:,.0f}", net=f"{net:+,.0f}", pct=f"{net / invested * 100:+.1f}")
    x = xirr(flows + [(now, final_value)])
    if x is not None and years >= 1:
        txt += t("ret.xirr_tail", x=f"{x * 100:+.1f}", extra=extra)
    else:
        txt += t("ret.under_year")
    return txt, start, years


def compute(show_t212=True, show_xtb=True):
    from t212_api import fetch_fx_rate, load_cached_snapshot
    from xtb_positions import xtb_rows

    now = datetime.now(timezone.utc)
    from portfolio_model import fx as _pfx
    base = _base_ccy()
    snap = load_cached_snapshot() or {}
    t212, xtb, xtb_flows, xtb_value = [], [], [], 0.0
    if show_t212 and snap.get("positions"):
        inst = {i["ticker"]: i for i in snap["instruments"]}
        for p in snap["positions"]:
            ccy, px = inst[p["ticker"]]["currencyCode"], p["currentPrice"]
            if ccy == "GBX":
                px, ccy = px / 100, "GBP"
            value = p["quantity"] * px * _pfx(ccy, base)
            t212.append((value - p["ppl"], p["ppl"], _age(p["initialFillDate"], now)))
    if show_xtb:
        for r in xtb_rows():
            f = _pfx(r["account_currency"], base)
            if r.get("initialFillDate") and r.get("cost_account"):
                cost, pl = r["cost_account"] * f, r["pl_account"] * f
                xtb.append((cost, pl, _age(r["initialFillDate"], now)))
                xtb_flows.append((_parse(r["initialFillDate"]), -cost))
                xtb_value += cost + pl

    lines, notes, ref = [], [], None
    data = _flows() if show_t212 else None
    t212_flows, t212_total = None, None
    if data and data.get("flows"):
        cash = snap.get("cash") or {}
        t212_total = cash.get("total")
        if t212_total is None:
            t212_total = sum(cash.get(k) or 0 for k in ("free", "invested", "ppl", "pieCash"))
        t212_flows = [(_parse(x["t"]), -x["amount"] if x["type"] == "DEPOSIT" else x["amount"]) for x in data["flows"]]

    if show_t212:
        res = _xirr_line("Trading 212", t212_flows, t212_total, now, t("ret.exact"), ccy=base) if t212_flows else None
        if res:
            lines.append(res[0])
            ref = (res[1], res[2])
        else:
            if show_t212 and not data:
                notes.append(t("ret.loading"))
            est = _estimate("Trading 212", t212, base)
            if est:
                lines.append(est)
    if show_xtb:
        est = _estimate("XTB", xtb, base)
        if est:
            lines.append(est)
    if show_t212 and show_xtb and t212_flows:
        res = _xirr_line("Total", t212_flows + xtb_flows, t212_total + xtb_value, now, t("ret.estimate_tag"), ccy=base)
        if res:
            lines.append(res[0])
    elif show_t212 and show_xtb:
        est = _estimate("Total", t212 + xtb, base)
        if est:
            lines.append(est)
    if ref:
        notes.insert(0, t("ret.ref", d=f"{ref[0]:%d.%m.%Y}", y=f"{ref[1]:.2f}"))
    return lines, notes


def render_returns_summary(show_t212=True, show_xtb=True):
    with st.expander(t("ret.title"), expanded=False):
        try:
            lines, notes = compute(show_t212, show_xtb)
        except Exception as e:
            st.caption(t("ret.err", e=e))
            return
        for ln in lines:
            st.markdown(ln)
        for n in notes:
            st.caption(n)
        st.caption(t("ret.xirr_q"), help=t("ret.xirr_help"))
        st.caption(t("ret.foot"))
