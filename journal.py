"""Jurnalul operatiunilor de cont (fara UI): depuneri, retrageri, dividende, dobanzi, cumparari/vanzari.
Surse: operatiunile de cash din exporturile XTB; la T212 tranzactiile de cont (t212_flows.json: depuneri,
retrageri, comisioane, dobanzi, transferuri), platile de dividende (dividends_cache.json, campul "payments")
si ordinele executate cu comisioanele lor (t212_fills.json)."""
from datetime import date, datetime

TYPES = ("deposit", "withdrawal", "dividend", "tax", "interest", "fee", "buy", "sell", "other")

_XTB_TYPES = {
    "deposit": "deposit",
    "withdrawal": "withdrawal",
    "dividend": "dividend",
    "withholding tax": "tax",
    "free funds interest": "interest",
    "free funds interest tax": "tax",
    "stock purchase": "buy",
    "stock sale": "sell",
    "commission": "fee",
}
_T212_TYPES = {"DEPOSIT": "deposit", "WITHDRAW": "withdrawal", "FEE": "fee",
               "INTEREST_ON_FREE_CASH": "interest", "LENDING_INTEREST": "interest"}


def _day(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def xtb_type(raw):
    return _XTB_TYPES.get(str(raw or "").strip().lower(), "other")


def xtb_operations(data):
    """Operatiunile din datele XTB (formatul din xtb.load_xtb())."""
    accounts = data.get("accounts") or {}
    out = []
    for key, ops in (data.get("cash_ops") or {}).items():
        acc = accounts.get(key) or {}
        ccy = acc.get("currency") or key.split("-")[0]
        label = acc.get("label") or "XTB " + ccy
        for op in (ops or {}).values():
            d = _day(op.get("time"))
            if d is None:
                continue
            out.append({
                "date": d, "account": label, "type": xtb_type(op.get("type")), "raw_type": op.get("type") or "",
                "instrument": op.get("instrument") or op.get("ticker") or "", "ticker": op.get("ticker") or "",
                "amount": op.get("amount"), "ccy": ccy, "comment": op.get("comment") or "",
            })
    return out


def _signed(kind, f):
    """Suma cu semn: iesirile (retrageri, comisioane) negative, intrarile pozitive, transferurile ca in API."""
    amount = abs(float(f.get("amount") or 0))
    if kind in ("withdrawal", "fee"):
        return -amount
    if kind in ("deposit", "interest"):
        return amount
    return float(f["signed"]) if f.get("signed") is not None else amount


def t212_operations(flows, dividends, ccy, names=None, fills=None):
    """flows: t212_flows.json; dividends: dividends_cache.json; fills: t212_fills.json; ccy: moneda contului T212."""
    names = names or {}
    ccy = ccy or ""
    out = []
    for f in (flows or {}).get("flows") or []:
        d = _day(f.get("t"))
        if d is None:
            continue
        kind = _T212_TYPES.get(f.get("type"), "other")
        out.append({"date": d, "account": "Trading 212", "type": kind, "raw_type": f.get("type") or "",
                    "instrument": "", "ticker": "", "amount": _signed(kind, f),
                    "ccy": f.get("ccy") or ccy, "comment": ""})
    for f in (fills or {}).get("fills") or []:
        d = _day(f.get("time"))
        if d is None or (f.get("ftype") or "TRADE") != "TRADE":
            continue
        ticker = f.get("ticker") or ""
        name = names.get(ticker) or _symbol(ticker)
        sell = f.get("side") == "SELL" or float(f.get("qty") or 0) < 0
        net = abs(float(f.get("net") or 0))
        wccy = f.get("wccy") or ccy
        out.append({"date": d, "account": "Trading 212", "type": "sell" if sell else "buy", "raw_type": f.get("side") or "",
                    "instrument": name, "ticker": ticker, "amount": net if sell else -net, "ccy": wccy,
                    "comment": "%g @ %g" % (abs(float(f.get("qty") or 0)), float(f.get("price") or 0))})
        for tx in f.get("taxes") or []:
            out.append({"date": _day(tx.get("time")) or d, "account": "Trading 212", "type": "fee",
                        "raw_type": tx.get("name") or "", "instrument": name, "ticker": ticker,
                        "amount": -abs(float(tx.get("amount") or 0)), "ccy": tx.get("ccy") or wccy,
                        "comment": _fee_name(tx.get("name"))})
    for ticker, info in ((dividends or {}).get("dividends") or {}).items():
        for p in (info or {}).get("payments") or []:
            d = _day(p.get("paidOn"))
            if d is None:
                continue
            out.append({"date": d, "account": "Trading 212", "type": "dividend", "raw_type": "DIVIDEND",
                        "instrument": names.get(ticker) or _symbol(ticker), "ticker": ticker,
                        "amount": p.get("amount"), "ccy": ccy, "comment": ""})
    return out


def _fee_name(name):
    from i18n import t
    key = "jr.fee." + str(name or "")
    label = t(key)
    return label if label != key else str(name or "").replace("_", " ").capitalize()


def _symbol(ticker):
    try:
        from yahoo import guess_yahoo_symbol
        return guess_yahoo_symbol(ticker) or ticker
    except Exception:
        return ticker


def filter_ops(ops, types=None, accounts=None, start=None, end=None):
    """Operatiunile cu tipul si contul cerute, intre start si end (inclusiv), cele mai noi primele."""
    res = [op for op in ops
           if (types is None or op["type"] in types)
           and (accounts is None or op["account"] in accounts)
           and (start is None or op["date"] >= start)
           and (end is None or op["date"] <= end)]
    return sorted(res, key=lambda op: (op["date"], op["account"]), reverse=True)


def totals(ops):
    """{(tip, moneda): (numar, suma)} pentru operatiunile date."""
    out = {}
    for op in ops:
        k = (op["type"], op["ccy"])
        n, s = out.get(k, (0, 0.0))
        out[k] = (n + 1, s + float(op["amount"] or 0))
    return out


def period_start(period, today=None):
    """Inceputul perioadei: '30d', '90d', 'ytd', '365d', 'all' (None)."""
    today = today or date.today()
    if period == "ytd":
        return date(today.year, 1, 1)
    if period.endswith("d"):
        from datetime import timedelta
        return today - timedelta(days=int(period[:-1]))
    return None


def load_all(names=None):
    """Toate operatiunile utilizatorului curent, din fisierele salvate (doar moneda T212 poate cere API-ul,
    cand cache-ul ei a expirat)."""
    ops = []
    try:
        import xtb
        ops += xtb_operations(xtb.load_xtb())
    except Exception:
        pass
    try:
        import returns_summary
        from core import load_config
        from t212_api import fetch_account_currency, load_cached_dividends
        cfg = load_config()
        if cfg.get("api_key_id") and cfg.get("api_secret"):
            ccy = fetch_account_currency(cfg.get("api_key_id"), cfg.get("api_secret"))[0]
            from core import load_json_file
            from t212_history_rebuild import FILLS_FILE
            ops += t212_operations(returns_summary._flows(), load_cached_dividends(), ccy, names,
                                   load_json_file(FILLS_FILE, {}))
    except Exception:
        pass
    return ops
