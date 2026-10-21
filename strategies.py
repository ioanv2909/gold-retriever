"""Lentile de strategie: ce ar spune un investitor value / growth / DDM / dividend growth / sentiment / event-driven
despre o actiune.

extract_metrics(tk, rf) citeste o data datele din Yahoo (serializabile, pentru cache); lens(name, m) le transforma
in scor X/100, verdict si semnale; convergence() numara lentilele pozitive si negative. Indicatori, nu recomandari.
"""
import math
import threading
import time
from datetime import date

import pandas as pd

from core import load_json_file, read_status, save_json_file, update_json_file
from dividend_score import annual_dividends, history_metrics
from scoring import indicator_score, safe_row
from userctx import UPath

STRATEGY_CACHE_FILE = UPath("strategy_cache.json", shared=True)
STRATEGY_STATUS_FILE = UPath("strategy_status.json", shared=True)
STRATEGY_REFRESH_INTERVAL = 86400
VERSION = 2             # se mareste cand se adauga metrici: intrarile vechi se recalculeaza
MARKET_KEY = "_market"  # contextul pietei (VIX, S&P 500 fata de SMA200), in acelasi cache

LENSES = ("value", "growth", "ddm", "div_growth", "sentiment", "events")
STRONG, WEAK = 65, 50   # aceleasi praguri ca la scorul de calitate
MIN_COVERAGE = 50

ERP = 5.0               # prima de risc a pietei (%), pentru CAPM
DEFAULT_RF = 4.0        # randamentul bondului la 10 ani daca ^TNX nu raspunde
TERMINAL_G = 3.0        # cresterea pe termen lung a dividendului (~ PIB nominal)
STAGE1_YEARS = 5
BETA_RANGE = (0.5, 2.0)
DDM_MIN_YIELD = 1.0     # sub acest randament dividendul nu explica pretul si DDM-ul nu are sens

VALUE_INDICATORS = [
    {"key": "pe_vs_hist", "weight": 20, "target": 0.8, "red_flag": 1.3, "higher_is_better": False},
    {"key": "fcf_yield", "weight": 25, "target": 6, "red_flag": 2, "higher_is_better": True},
    {"key": "ey_spread", "weight": 15, "target": 2, "red_flag": -2, "higher_is_better": True},
    # numarul Graham e foarte strict (aproape orice actiune de calitate e sub el): pondere mica, prag rosu larg
    {"key": "graham_upside", "weight": 10, "target": 0, "red_flag": -70, "higher_is_better": True},
    {"key": "piotroski", "weight": 20, "target": 7, "red_flag": 3, "higher_is_better": True},
    {"key": "ev_ebitda", "weight": 10, "target": 10, "red_flag": 20, "higher_is_better": False},
]
GROWTH_INDICATORS = [
    {"key": "rev_cagr", "weight": 20, "target": 15, "red_flag": 3, "higher_is_better": True},
    {"key": "eps_cagr", "weight": 15, "target": 15, "red_flag": 0, "higher_is_better": True},
    {"key": "rev_growth_fwd", "weight": 15, "target": 12, "red_flag": 2, "higher_is_better": True},
    {"key": "eps_growth_fwd", "weight": 15, "target": 15, "red_flag": 0, "higher_is_better": True},
    {"key": "eps_rev_90d", "weight": 15, "target": 3, "red_flag": -3, "higher_is_better": True},
    {"key": "peg", "weight": 10, "target": 1, "red_flag": 2.5, "higher_is_better": False},
    {"key": "rule_of_40", "weight": 10, "target": 40, "red_flag": 15, "higher_is_better": True},
]
DIV_GROWTH_INDICATORS = [
    {"key": "growth_streak", "weight": 25, "target": 10, "red_flag": 1, "higher_is_better": True},
    {"key": "dgr_3y", "weight": 10, "target": 7, "red_flag": 0, "higher_is_better": True},
    {"key": "dgr_5y", "weight": 20, "target": 7, "red_flag": 0, "higher_is_better": True},
    {"key": "dgr_10y", "weight": 10, "target": 6, "red_flag": 0, "higher_is_better": True},
    {"key": "chowder", "weight": 20, "target": 12, "red_flag": 6, "higher_is_better": True},
    {"key": "payout_trend", "weight": 15, "target": 0, "red_flag": 5, "higher_is_better": False},
]
SENTIMENT_INDICATORS = [
    {"key": "rating_net_90d", "weight": 15, "target": 2, "red_flag": -2, "higher_is_better": True},
    {"key": "target_net_90d", "weight": 15, "target": 50, "red_flag": -50, "higher_is_better": True},
    {"key": "eps_rev_90d", "weight": 15, "target": 3, "red_flag": -3, "higher_is_better": True},
    {"key": "rec_mean", "weight": 10, "target": 1.8, "red_flag": 3.0, "higher_is_better": False},
    {"key": "short_float", "weight": 10, "target": 2, "red_flag": 10, "higher_is_better": False},
    {"key": "short_change", "weight": 5, "target": -10, "red_flag": 20, "higher_is_better": False},
    # vanzarile de rutina ale conducerii sunt mici fata de capitalizare: abia vanzari mari scad scorul
    {"key": "insider_net", "weight": 10, "target": 0.01, "red_flag": -0.1, "higher_is_better": True},
    {"key": "inst_change", "weight": 10, "target": 2, "red_flag": -2, "higher_is_better": True},
    {"key": "news_tone", "weight": 10, "target": 40, "red_flag": -40, "higher_is_better": True},
]
EVENT_INDICATORS = [
    {"key": "beat_rate", "weight": 30, "target": 75, "red_flag": 40, "higher_is_better": True},
    {"key": "avg_surprise", "weight": 20, "target": 5, "red_flag": -2, "higher_is_better": True},
    {"key": "avg_reaction", "weight": 20, "target": 2, "red_flag": -2, "higher_is_better": True},
    {"key": "event_balance", "weight": 30, "target": 2, "red_flag": -2, "higher_is_better": True},
]
DDM_INDICATORS = [
    {"key": "ddm_margin", "weight": 100, "target": 10, "red_flag": -50, "higher_is_better": True},
]


# ---------------------------------------------------------------------------
# Citirea datelor (Yahoo -> dict serializabil)
# ---------------------------------------------------------------------------
def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _by_year(df, *names):
    """Un rand din situatiile financiare -> {an fiscal: valoare}, fara valori lipsa."""
    row = safe_row(df, *names)
    if row is None:
        return {}
    out = {}
    for col, v in row.items():
        v = _num(v)
        year = getattr(col, "year", None)
        if v is not None and year is not None:
            out[int(year)] = v
    return out


def _fin_price_scale(currency, fin_currency):
    """Factorul care aduce pretul in moneda situatiilor financiare, sau None daca monedele difera (ADR etc.)."""
    if not currency or not fin_currency:
        return None
    if currency == "GBp" and fin_currency == "GBP":
        return 0.01
    return 1.0 if currency.upper() == fin_currency.upper() and currency != "GBp" else None


def _cagr(series, max_years=4):
    """CAGR (%) intre cel mai nou an si cel mai vechi (cel mult max_years in urma); ambele pozitive, minim 3 ani."""
    years = sorted(series)
    if len(years) < 3:
        return None
    last = years[-1]
    first = min(y for y in years if y >= last - max_years)
    n = last - first
    if n < 2 or series[first] <= 0 or series[last] <= 0:
        return None
    return ((series[last] / series[first]) ** (1 / n) - 1) * 100


def _year_end_prices(monthly, years, fiscal_dates):
    """Pretul la sfarsitul fiecarui an fiscal, din istoricul lunar."""
    out = {}
    if monthly is None or len(monthly) == 0:
        return out
    idx = pd.DatetimeIndex(monthly.index).tz_localize(None) if getattr(monthly.index, "tz", None) else pd.DatetimeIndex(monthly.index)
    s = pd.Series(list(monthly.values), index=idx).dropna()
    for y in years:
        d = pd.Timestamp(fiscal_dates.get(y, date(y, 12, 31)))
        before = s[s.index <= d + pd.Timedelta(days=5)]
        if len(before) and (d - before.index[-1]).days < 45:
            out[y] = float(before.iloc[-1])
    return out


def piotroski(fin, bs, cf):
    """Piotroski F-score pe ultimii doi ani fiscali: (teste trecute, teste care s-au putut face)."""
    ni, rev, gp = _by_year(fin, "Net Income", "Net Income Common Stockholders"), _by_year(fin, "Total Revenue"), _by_year(fin, "Gross Profit")
    ta, ca, cl = _by_year(bs, "Total Assets"), _by_year(bs, "Current Assets"), _by_year(bs, "Current Liabilities")
    ltd = _by_year(bs, "Long Term Debt")
    sh = _by_year(bs, "Ordinary Shares Number", "Share Issued")
    cfo = _by_year(cf, "Operating Cash Flow")
    years = sorted(set(ni) & set(ta))
    if len(years) < 2:
        return None, 0
    t, p = years[-1], years[-2]

    def ratio(a, b, y):
        return a[y] / b[y] if y in a and b.get(y) else None

    def gt(x, y):
        return None if x is None or y is None else x > y

    roa_t, roa_p = ratio(ni, ta, t), ratio(ni, ta, p)
    lev_t = ltd.get(t, 0.0) / ta[t] if ta.get(t) else None
    lev_p = ltd.get(p, 0.0) / ta[p] if ta.get(p) else None
    tests = [
        gt(roa_t, 0),
        gt(cfo.get(t), 0),
        gt(roa_t, roa_p),
        gt(ratio(cfo, ta, t), roa_t),
        gt(lev_p, lev_t) if ltd else None,
        gt(ratio(ca, cl, t), ratio(ca, cl, p)),
        (sh[t] <= sh[p]) if t in sh and p in sh else None,
        gt(ratio(gp, rev, t), ratio(gp, rev, p)),
        gt(ratio(rev, ta, t), ratio(rev, ta, p)),
    ]
    done = [x for x in tests if x is not None]
    return sum(done), len(done)


def fetch_rf():
    """Randamentul bondului american la 10 ani (%), din ^TNX."""
    from yf_compat import yf, YFINANCE_AVAILABLE
    if not YFINANCE_AVAILABLE:
        return None
    try:
        close = yf.Ticker("^TNX").history(period="5d")["Close"].dropna()
        v = float(close.iloc[-1])
        return v / 10 if v > 20 else v
    except Exception:
        return None


def extract_metrics(tk, rf=None, today=None, symbol=None, ua_email=None, now=None, news_fn=None, edgar_fn=None):
    """Datele brute ale lentilelor, ca dict serializabil (pentru cache). ua_email: contactul pentru SEC EDGAR."""
    import signals
    import analysts
    info = tk.info or {}
    quote = str(info.get("quoteType") or "").upper()
    if quote in ("ETF", "MUTUALFUND"):
        return {"v": VERSION, "kind": "etf"}

    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    fin, bs, cf = safe(lambda: tk.financials), safe(lambda: tk.balance_sheet), safe(lambda: tk.cashflow)
    currency, fin_ccy = info.get("currency"), info.get("financialCurrency") or info.get("currency")
    scale = _fin_price_scale(currency, fin_ccy)
    price = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
    price_fin = price * scale if price is not None and scale is not None else None

    eps = _by_year(fin, "Diluted EPS", "Basic EPS")
    rev = _by_year(fin, "Total Revenue", "Operating Revenue")
    fcf = _by_year(cf, "Free Cash Flow")
    shares = _by_year(bs, "Ordinary Shares Number", "Share Issued")
    equity = _by_year(bs, "Stockholders Equity", "Common Stock Equity")
    fiscal_dates = {}
    for col in (fin.columns if isinstance(fin, pd.DataFrame) else []):
        if getattr(col, "year", None):
            fiscal_dates[int(col.year)] = col

    m = {"v": VERSION, "kind": "stock", "currency": currency, "fin_currency": fin_ccy, "price": price, "rf": rf}

    # value
    pe = _num(info.get("trailingPE"))
    m["pe"] = pe if pe and pe > 0 else None
    pe_hist = None
    if scale is not None:
        monthly = safe(lambda: tk.history(period="6y", interval="1mo", auto_adjust=False)["Close"])
        prices = _year_end_prices(monthly, [y for y, v in eps.items() if v > 0], fiscal_dates)
        pes = [prices[y] * scale / eps[y] for y in prices]
        pe_hist = float(pd.Series(pes).median()) if len(pes) >= 3 else None
    m["pe_hist"] = pe_hist
    m["pe_vs_hist"] = m["pe"] / pe_hist if m["pe"] and pe_hist else None
    last_fcf_year = max(fcf) if fcf else None
    m["fcf_yield"] = (fcf[last_fcf_year] / shares[last_fcf_year] / price_fin * 100
                      if last_fcf_year and shares.get(last_fcf_year) and price_fin else None)
    m["ey_spread"] = (100 / m["pe"] - rf) if m["pe"] and rf is not None else None
    last_eps_year = max(eps) if eps else None
    graham = None
    if last_eps_year and eps[last_eps_year] > 0 and equity.get(last_eps_year, 0) > 0 and shares.get(last_eps_year):
        graham = math.sqrt(22.5 * eps[last_eps_year] * equity[last_eps_year] / shares[last_eps_year])
    m["graham"] = graham / scale if graham and scale else None
    m["graham_upside"] = (graham / price_fin - 1) * 100 if graham and price_fin else None
    m["piotroski"], m["piotroski_n"] = piotroski(fin, bs, cf)
    ev = _num(info.get("enterpriseToEbitda"))
    m["ev_ebitda"] = ev if ev and ev > 0 else None

    # growth
    m["rev_cagr"] = _cagr(rev)
    m["eps_cagr"] = _cagr(eps)
    rev_est = analysts.parse_estimates(safe(lambda: tk.revenue_estimate))
    eps_est = analysts.parse_estimates(safe(lambda: tk.earnings_estimate))
    m["rev_growth_fwd"] = (rev_est.get("+1y") or rev_est.get("0y") or {}).get("growth")
    m["eps_growth_fwd"] = (eps_est.get("+1y") or eps_est.get("0y") or {}).get("growth")
    trend = analysts.parse_eps_trend(safe(lambda: tk.eps_trend), None)
    m["eps_rev_90d"] = (trend.get("0y") or {}).get("chg_90d")
    peg = _num(info.get("trailingPegRatio") or info.get("pegRatio"))
    m["peg"] = peg if peg and peg > 0 else None
    years = sorted(rev)
    rg1 = (rev[years[-1]] / rev[years[-2]] - 1) * 100 if len(years) >= 2 and rev[years[-2]] > 0 else None
    fcf_margin = fcf[years[-1]] / rev[years[-1]] * 100 if years and years[-1] in fcf and rev[years[-1]] > 0 else None
    m["rule_of_40"] = rg1 + fcf_margin if rg1 is not None and fcf_margin is not None else None

    # dividende (in moneda de cotare, ca pretul)
    annual = annual_dividends(safe(lambda: tk.dividends), today)
    m["annual_div"] = {str(y): v for y, v in annual.items()}
    m["eps_hist"] = {str(y): v * (1 / scale) for y, v in eps.items()} if scale else {}
    y = _num(info.get("dividendYield"))  # Yahoo il da deja ca procent
    m["div_yield"] = y if y else None
    payout, roe = _num(info.get("payoutRatio")), _num(info.get("returnOnEquity"))
    m["payout"] = payout * 100 if payout and payout > 0 else None
    m["roe"] = roe * 100 if roe is not None else None
    m["beta"] = _num(info.get("beta"))

    # sentiment si evenimente
    m.update(signals.extract(tk, symbol or str(info.get("symbol") or ""), info, now=now, ua_email=ua_email,
                             news_fn=news_fn, edgar_fn=edgar_fn))
    return m


# ---------------------------------------------------------------------------
# Lentile
# ---------------------------------------------------------------------------
def _score(indicators, values):
    rows, points, coverage = [], 0.0, 0.0
    for ind in indicators:
        val = values.get(ind["key"])
        score = None if val is None else indicator_score(val, ind["target"], ind["red_flag"], ind["higher_is_better"])
        if score is not None:
            points += score * ind["weight"]
            coverage += ind["weight"]
        rows.append(dict(ind, value=val, score=score))
    return rows, (points / coverage * 100 if coverage else None), coverage


def _level(total, coverage):
    if total is None or coverage < MIN_COVERAGE:
        return "insufficient"
    return "strong" if total >= STRONG else "mixed" if total >= WEAK else "weak"


def _result(lens, indicators, values, extra=None):
    rows, total, coverage = _score(indicators, values)
    return {"lens": lens, "applicable": True, "rows": rows, "total": total, "coverage": coverage,
            "level": _level(total, coverage), "extra": extra or {}}


def _na(lens, reason):
    return {"lens": lens, "applicable": False, "reason": reason, "rows": [], "total": None, "coverage": 0.0,
            "level": "na", "extra": {}}


def _annual(m):
    return {int(y): float(v) for y, v in (m.get("annual_div") or {}).items()}


def _dgr(annual, n, last):
    if annual.get(last, 0) > 0 and annual.get(last - n, 0) > 0:
        return ((annual[last] / annual[last - n]) ** (1 / n) - 1) * 100
    return None


def growth_streak(annual, last):
    """Ani consecutivi cu dividend anual mai mare decat anul anterior."""
    n = 0
    while annual.get(last - n, 0) > 0 and annual.get(last - n - 1, 0) > 0 and annual[last - n] >= annual[last - n - 1] * 1.001:
        n += 1
    return n


def payout_trend(annual, eps_hist):
    """Panta payout-ului (dividend / EPS) in puncte procentuale pe an; minim trei ani cu EPS pozitiv."""
    pts = sorted((y, annual[y] / e * 100) for y, e in eps_hist.items() if e > 0 and annual.get(y, 0) > 0)
    if len(pts) < 3:
        return None
    (y0, p0), (y1, p1) = pts[0], pts[-1]
    return (p1 - p0) / (y1 - y0)


def value_lens(m, quality=None):
    vals = dict(m)
    # la banci etc. lipsesc unele teste Piotroski: scorul se aduce la scara 0-9, dar doar cu minim 6 teste
    n = m.get("piotroski_n") or 0
    vals["piotroski"] = m["piotroski"] * 9 / n if n >= 6 and m.get("piotroski") is not None else None
    r = _result("value", VALUE_INDICATORS, vals, {"pe": m.get("pe"), "pe_hist": m.get("pe_hist"),
                                                  "graham": m.get("graham"), "piotroski_raw": m.get("piotroski"),
                                                  "piotroski_n": n, "rf": m.get("rf")})
    if r["level"] == "strong" and quality is not None and quality < WEAK:
        r["level"] = "trap"  # ieftina, dar scorul de calitate e slab: posibila capcana de valoare
    return r


def growth_lens(m):
    return _result("growth", GROWTH_INDICATORS, m)


def div_growth_lens(m, today=None):
    annual = _annual(m)
    last = (today or date.today()).year - 1
    if not annual or annual.get(last, 0) <= 0:
        return _na("div_growth", "no_dividend")
    hist = history_metrics(annual, today)
    vals = {
        "growth_streak": growth_streak(annual, last),
        "dgr_3y": _dgr(annual, 3, last), "dgr_5y": hist["div_cagr_5y"], "dgr_10y": _dgr(annual, 10, last),
        "payout_trend": payout_trend(annual, {int(y): v for y, v in (m.get("eps_hist") or {}).items()}),
    }
    yld = m.get("div_yield")
    indicators = [dict(i) for i in DIV_GROWTH_INDICATORS]
    if yld is not None and vals["dgr_5y"] is not None:
        vals["chowder"] = yld + vals["dgr_5y"]
        # regula Chowder: randament + DGR 5 ani >= 12 pentru randament de cel putin 3%, altfel >= 15
        need = 12 if yld >= 3 else 15
        for i in indicators:
            if i["key"] == "chowder":
                i.update(target=need, red_flag=need - 6)
    return _result("div_growth", indicators, vals, {"years_paid": hist["years_paid"], "cuts_10y": hist["cuts_10y"],
                                                    "div_yield": yld})


def sentiment_lens(m):
    return _result("sentiment", SENTIMENT_INDICATORS, m, {
        k: m.get(k) for k in ("upgrades", "downgrades", "raises", "lowers", "analysts_n", "insider_buys",
                              "insider_sells", "news_n")})


def events_lens(m):
    return _result("events", EVENT_INDICATORS, m, {
        "earnings_n": m.get("earnings_n"), "event_n": m.get("event_n"), "sec_checked": m.get("sec_checked"),
        "events": m.get("events") or []})


def ddm_value(d0, r, g1, g2, years=STAGE1_YEARS):
    """DDM in doua etape: g1 timp de `years` ani, apoi Gordon cu g2. r, g in %. None daca r <= g2."""
    r, g1, g2 = r / 100, g1 / 100, g2 / 100
    if r <= g2:
        return None
    pv, d = 0.0, d0
    for t in range(1, years + 1):
        d *= 1 + g1
        pv += d / (1 + r) ** t
    return pv + d * (1 + g2) / (r - g2) / (1 + r) ** years


def ddm_lens(m, today=None, erp=ERP):
    annual = _annual(m)
    last = (today or date.today()).year - 1
    hist = history_metrics(annual, today)
    if not annual or annual.get(last, 0) <= 0:
        return _na("ddm", "no_dividend")
    if (hist["years_paid"] or 0) < 5:
        return _na("ddm", "short_history")
    if (hist["cuts_10y"] or 0) >= 2:
        return _na("ddm", "irregular")
    if m.get("div_yield") is not None and m["div_yield"] < DDM_MIN_YIELD:
        return _na("ddm", "low_yield")
    price = m.get("price")
    if not price:
        return _na("ddm", "no_price")
    rf = m.get("rf") if m.get("rf") is not None else DEFAULT_RF
    beta = min(max(m.get("beta") if m.get("beta") is not None else 1.0, BETA_RANGE[0]), BETA_RANGE[1])
    r = rf + beta * erp
    g_hist = hist["div_cagr_5y"]
    roe, payout = m.get("roe"), m.get("payout")
    g_sust = roe * (1 - payout / 100) if roe is not None and payout is not None and payout < 100 else None
    gs = [g for g in (g_hist, g_sust) if g is not None]
    if not gs:
        return _na("ddm", "no_growth")
    g1 = min(max(min(gs), 0.0), 12.0)
    g2 = min(g1, TERMINAL_G, r - 1)
    d0 = annual[last]
    value = ddm_value(d0, r, g1, g2)
    if not value or not 0.05 < value / price < 20:
        return _na("ddm", "units")  # dividende si pret in unitati diferite (ex. GBP / pence) sau date gresite
    sens = {}
    for dr in (-1, 0, 1):
        for dg in (-1, 0, 1):
            g1s, g2s = max(g1 + dg, 0.0), max(g2 + dg, 0.0)
            v = ddm_value(d0, r + dr, g1s, g2s) if r + dr - g2s >= 0.5 else None
            sens["%d,%d" % (dr, dg)] = v
    margin = (value / price - 1) * 100
    return _result("ddm", DDM_INDICATORS, {"ddm_margin": margin}, {
        "value": value, "price": price, "margin": margin, "d0": d0, "rf": rf, "beta": beta, "erp": erp, "r": r,
        "g1": g1, "g2": g2, "g_hist": g_hist, "g_sust": g_sust, "sens": sens})


def evaluate(m, quality=None, today=None):
    """Toate lentilele pentru o intrare din cache. ETF-urile si intrarile fara date sunt N/A."""
    if not m or m.get("kind") == "etf":
        reason = "etf" if m and m.get("kind") == "etf" else "no_data"
        return {lens: _na(lens, reason) for lens in LENSES}
    return {"value": value_lens(m, quality), "growth": growth_lens(m), "ddm": ddm_lens(m, today),
            "div_growth": div_growth_lens(m, today), "sentiment": sentiment_lens(m), "events": events_lens(m)}


def convergence(results):
    """(pozitive, negative, cu date): cate lentile sunt de acord. "trap" conteaza ca negativa."""
    pos = sum(1 for r in results.values() if r["level"] == "strong")
    neg = sum(1 for r in results.values() if r["level"] in ("weak", "trap"))
    known = sum(1 for r in results.values() if r["level"] in ("strong", "mixed", "weak", "trap"))
    return pos, neg, known


# ---------------------------------------------------------------------------
# Cache si job de fundal
# ---------------------------------------------------------------------------
def load_cache():
    return load_json_file(STRATEGY_CACHE_FILE, {})


def load_status():
    return read_status(STRATEGY_STATUS_FILE)


def _stale(entry, now):
    if entry.get("fetched_at") is None or entry.get("v") != VERSION:
        return True
    return now - float(entry["fetched_at"]) >= STRATEGY_REFRESH_INTERVAL


def run_context():
    """Datele comune unui tur: randamentul bondului, contactul SEC, contextul pietei."""
    import signals
    return {"rf": fetch_rf(), "ua": signals.ua_email(), "market": signals.market_context()}


def fetch_one(symbol, ctx):
    from yf_compat import yf, YFINANCE_AVAILABLE
    if not YFINANCE_AVAILABLE:
        return None, "yfinance indisponibil"
    try:
        return extract_metrics(yf.Ticker(symbol), ctx.get("rf"), symbol=symbol, ua_email=ctx.get("ua")), None
    except Exception as e:
        return None, str(e)[:200]


def fetch_and_cache(tickers, resolve=None, now=None, sleep=1.0, fetch=None, ctx_fn=None):
    """Recalculeaza tickerele lipsa sau mai vechi de o zi."""
    if resolve is None:
        from yahoo import resolve_yahoo_symbol as resolve
    fetch, ctx_fn = fetch or fetch_one, ctx_fn or run_context
    now = now if now is not None else time.time()
    cache = load_cache()
    todo = [t for t in tickers if _stale(cache.get(t) or {}, now)]
    total = len(todo)
    save_json_file(STRATEGY_STATUS_FILE, {"in_progress": True, "started_at": now, "total": total, "done": 0})
    try:
        ctx = ctx_fn() if todo else {}
        if todo:
            market = dict(ctx.get("market") or {}, fetched_at=now)
            update_json_file(STRATEGY_CACHE_FILE, {}, lambda c: dict(c, **{MARKET_KEY: market}))
        for idx, ticker in enumerate(todo):
            symbol = resolve(ticker)
            m, err = fetch(symbol, ctx)
            entry = {"symbol": symbol, "fetched_at": now, "v": VERSION, "m": m}
            if err:
                entry["error"] = err
            update_json_file(STRATEGY_CACHE_FILE, {}, lambda c, t=ticker, e=entry: dict(c, **{t: e}))
            save_json_file(STRATEGY_STATUS_FILE, {"in_progress": True, "started_at": None, "total": total, "done": idx + 1})
            if sleep and idx < total - 1:
                time.sleep(sleep)
    finally:
        save_json_file(STRATEGY_STATUS_FILE, {"in_progress": False, "started_at": None, "total": total, "done": total})
    return load_cache()


def start_fetch_background(tickers):
    if load_status().get("in_progress"):
        return False
    threading.Thread(target=fetch_and_cache, args=(list(tickers),), daemon=True).start()
    return True
