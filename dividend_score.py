"""Scor de dividend (0-100) pe patru piloni: siguranta, crestere, consecventa, randament."""
from datetime import date

import pandas as pd

from scoring import indicator_score, safe_row

INDICATORS = [
    {"key": "payout_ratio", "pillar": "safety", "label": "Payout Ratio (%)",
     "weight": 15, "target": 60, "red_flag": 90, "higher_is_better": False},
    {"key": "fcf_payout", "pillar": "safety", "label": "FCF Payout (%)",
     "weight": 20, "target": 60, "red_flag": 100, "higher_is_better": False},
    {"key": "div_cagr_5y", "pillar": "growth", "label": "Dividend CAGR 5y (%)",
     "weight": 20, "target": 7, "red_flag": 0, "higher_is_better": True},
    {"key": "years_paid", "pillar": "consistency", "label": "Years paid (consecutive)",
     "weight": 15, "target": 10, "red_flag": 3, "higher_is_better": True},
    {"key": "cuts_10y", "pillar": "consistency", "label": "Cuts in 10 years",
     "weight": 15, "target": 0, "red_flag": 2, "higher_is_better": False},
    {"key": "dividend_yield", "pillar": "yield", "label": "Dividend Yield (%)",
     "weight": 15, "target": 3, "red_flag": 0.5, "higher_is_better": True},
]
PILLARS = ("safety", "growth", "consistency", "yield")
YIELD_TRAP = 8.0   # peste acest randament, piata se asteapta de obicei la o taiere
CUT_DROP = 0.9     # scadere de peste 10% a dividendului anual = taiere


def annual_dividends(series, today=None):
    """Suma dividendelor pe ani calendaristici incheiati: {an: suma}."""
    today = today or date.today()
    if series is None or len(series) == 0:
        return {}
    s = pd.Series(series)
    years = [getattr(i, "year", None) for i in s.index]
    out = {}
    for y, v in zip(years, s.values):
        if y is not None and y < today.year and v == v:
            out[y] = out.get(y, 0.0) + float(v)
    return out


def history_metrics(annual, today=None):
    """CAGR pe 5 ani, ani consecutivi cu dividend si numarul de taieri din ultimii 10 ani."""
    today = today or date.today()
    last = today.year - 1
    m = {"div_cagr_5y": None, "years_paid": None, "cuts_10y": None}
    if not annual or annual.get(last, 0) <= 0:
        return m
    n = 0
    while annual.get(last - n, 0) > 0:
        n += 1
    m["years_paid"] = n
    start = annual.get(last - 5, 0)
    if start > 0:
        m["div_cagr_5y"] = ((annual[last] / start) ** (1 / 5) - 1) * 100
    if n >= 2:
        cuts, prev_cut = 0, False
        for y in range(max(last - 9, last - n + 2), last + 1):
            # o plata mutata peste an da un an mai mic urmat de unul mai mare: reperul e minimul
            # ultimilor doi ani, iar o scadere recuperata anul urmator nu se numara
            ref = min(annual[y - 1], annual.get(y - 2) or annual[y - 1])
            nxt = annual.get(y + 1)
            cut = annual[y] < CUT_DROP * ref and (nxt is None or nxt < CUT_DROP * ref)
            # o taiere care se intinde pe doi ani calendaristici se numara o data
            cuts += cut and not prev_cut
            prev_cut = cut
        m["cuts_10y"] = cuts
    return m


def yield_score(value):
    """Ca indicatorii obisnuiti, dar un randament foarte mare scade scorul (posibila capcana)."""
    base = indicator_score(value, 3, 0.5, True)
    if base is None or value <= YIELD_TRAP:
        return base
    return max(0.0, 1.0 - (value - YIELD_TRAP) / YIELD_TRAP)


def fcf_payout(cashflow):
    """Dividende platite / free cash flow, pe ultimul an fiscal, in %. info["freeCashflow"] e "levered" si nu e bun aici."""
    fcf_row = safe_row(cashflow, "Free Cash Flow")
    div_row = safe_row(cashflow, "Cash Dividends Paid", "Common Stock Dividend Paid")
    if fcf_row is None or div_row is None:
        return None
    for col in fcf_row.index:
        fcf, paid = fcf_row.get(col), div_row.get(col)
        if pd.isna(fcf) or pd.isna(paid):
            continue
        paid = abs(float(paid))
        if not paid:
            return None
        # FCF negativ: dividendul vine din datorii sau rezerve, deci zona rosie
        return paid / float(fcf) * 100 if fcf > 0 else 200.0
    return None


def extract_dividend_metrics(tk, today=None):
    """Metricile din yfinance. Intoarce (metrics, pays) - pays=False daca firma nu plateste dividend."""
    info = tk.info or {}
    annual = annual_dividends(tk.dividends, today)
    m = history_metrics(annual, today)
    rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
    pays = bool(rate) or m["years_paid"] is not None
    payout = info.get("payoutRatio")
    m["payout_ratio"] = payout * 100 if payout is not None and payout > 0 else None
    m["fcf_payout"] = fcf_payout(tk.cashflow)
    y = info.get("dividendYield")  # Yahoo il da deja ca procent
    m["dividend_yield"] = float(y) if y else None
    return m, pays


def compute_dividend_score(metrics):
    rows, points, coverage = [], 0.0, 0.0
    pillar = {p: [0.0, 0.0] for p in PILLARS}
    for ind in INDICATORS:
        val = metrics.get(ind["key"])
        if val is None or pd.isna(val):
            score = None
        elif ind["key"] == "dividend_yield":
            score = yield_score(val)
        else:
            score = indicator_score(val, ind["target"], ind["red_flag"], ind["higher_is_better"])
        if score is not None:
            points += score * ind["weight"]
            coverage += ind["weight"]
            pillar[ind["pillar"]][0] += score * ind["weight"]
            pillar[ind["pillar"]][1] += ind["weight"]
        rows.append(dict(ind, value=val, score=score, points=score * ind["weight"] if score is not None else None))
    total = points / coverage * 100 if coverage else 0.0
    if coverage < 50:
        rating = "Date insuficiente"
    elif total >= 80:
        rating = "Excelent"
    elif total >= 65:
        rating = "Aprobat"
    elif total >= 50:
        rating = "Vulnerabil"
    else:
        rating = "Respins"
    return {
        "rows": rows, "total": total, "coverage": coverage, "rating": rating,
        "pillars": {p: (v[0] / v[1] * 100 if v[1] else None) for p, v in pillar.items()},
    }
