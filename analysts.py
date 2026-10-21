"""Tinte de pret, recomandari, estimari si revizuiri ale analistilor, din yfinance."""
import math

import pandas as pd

REC_COLS = ("strongBuy", "buy", "hold", "sell", "strongSell")
EST_PERIODS = ("0q", "+1q", "0y", "+1y")


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _int(v):
    f = _num(v)
    return int(f) if f is not None else None


def parse_targets(raw, scale=1.0):
    """dict yfinance analyst_price_targets -> {low, mean, median, high, current}; None daca lipseste media."""
    if not isinstance(raw, dict):
        return None
    out = {k: (_num(raw.get(k)) / scale if _num(raw.get(k)) is not None else None)
           for k in ("low", "mean", "median", "high", "current")}
    return out if out["mean"] else None


def upside(target, price):
    return (target / price - 1) * 100 if target and price else None


def parse_recommendations(df):
    """Ultimele luni de recomandari: [{period, strongBuy, ..., total}], cea mai recenta prima."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        row = {"period": str(r.get("period", ""))}
        row.update({c: _int(r.get(c)) or 0 for c in REC_COLS})
        row["total"] = sum(row[c] for c in REC_COLS)
        if row["total"]:
            out.append(row)
    return out


def parse_estimates(df):
    """earnings_estimate / revenue_estimate -> {perioada: {avg, low, high, n, year_ago, growth, currency}}.
    Valorile in GBp (pence) se trec in GBP."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    out = {}
    for p in EST_PERIODS:
        if p not in df.index:
            continue
        r = df.loc[p]
        ccy = str(r.get("currency") or "")
        scale = 100.0 if ccy == "GBp" else 1.0
        avg = _num(r.get("avg"))
        if avg is None:
            continue
        ago = _num(r.get("yearAgoEps") if "yearAgoEps" in r.index else r.get("yearAgoRevenue"))
        g = _num(r.get("growth"))
        out[p] = {
            "avg": avg / scale,
            "low": _num(r.get("low")) / scale if _num(r.get("low")) is not None else None,
            "high": _num(r.get("high")) / scale if _num(r.get("high")) is not None else None,
            "n": _int(r.get("numberOfAnalysts")),
            "year_ago": ago / scale if ago is not None else None,
            "growth": g * 100 if g is not None else None,
            "currency": "GBP" if ccy == "GBp" else ccy,
        }
    return out


def parse_eps_trend(trend, revisions):
    """Cat s-a schimbat estimarea EPS fata de acum 30 si 90 de zile (%), plus revizuirile in sus/jos din 30 de zile."""
    out = {}
    if isinstance(trend, pd.DataFrame) and not trend.empty:
        for p in EST_PERIODS:
            if p not in trend.index:
                continue
            r = trend.loc[p]
            cur = _num(r.get("current"))
            row = {"current": cur}
            for col, key in (("30daysAgo", "chg_30d"), ("90daysAgo", "chg_90d")):
                old = _num(r.get(col))
                row[key] = (cur / old - 1) * 100 if cur is not None and old else None
            out[p] = row
    if isinstance(revisions, pd.DataFrame) and not revisions.empty:
        for p in EST_PERIODS:
            if p in revisions.index:
                r = revisions.loc[p]
                row = out.setdefault(p, {"current": None, "chg_30d": None, "chg_90d": None})
                row["up_30d"] = _int(r.get("upLast30days"))
                row["down_30d"] = _int(r.get("downLast30days"))
    return out


def parse_rating_changes(df, limit=10, scale=1.0):
    """Ultimele schimbari de rating: [{date, firm, action, from, to, target, prior_target}]."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    df = df.sort_index(ascending=False).head(limit)
    out = []
    for idx, r in df.iterrows():
        tgt, prior = _num(r.get("currentPriceTarget")), _num(r.get("priorPriceTarget"))
        out.append({
            "date": str(idx)[:10],
            "firm": str(r.get("Firm") or ""),
            "action": str(r.get("Action") or ""),
            "from": str(r.get("FromGrade") or ""),
            "to": str(r.get("ToGrade") or ""),
            "target": tgt / scale if tgt else None,
            "prior_target": prior / scale if prior else None,
        })
    return out


def fetch_analyst_data(tk, scale=1.0):
    """Toate datele, ca dict serializabil. Fiecare parte esueaza separat (multe tickere nu au toate datele)."""
    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    return {
        "targets": parse_targets(safe(lambda: tk.analyst_price_targets), scale),
        "recommendations": parse_recommendations(safe(lambda: tk.recommendations)),
        "eps": parse_estimates(safe(lambda: tk.earnings_estimate)),
        "revenue": parse_estimates(safe(lambda: tk.revenue_estimate)),
        "eps_trend": parse_eps_trend(safe(lambda: tk.eps_trend), safe(lambda: tk.eps_revisions)),
        "changes": parse_rating_changes(safe(lambda: tk.upgrades_downgrades), scale=scale),
    }


def has_data(d):
    return bool(d and (d.get("targets") or d.get("recommendations") or d.get("eps")))
