"""Date pentru lentilele Sentiment si Event-driven.

Sentiment: schimbari de rating si de tinta (90 de zile), recomandarea medie, short interest, tranzactii ale
insiderilor (6 luni), schimbarea detinerilor institutionale, tonul titlurilor de stiri (cuvinte-cheie).
Evenimente: istoricul surprizelor la earnings si reactia pretului, rapoarte 8-K din SEC EDGAR (doar companii
americane), stiri clasificate pe categorii (M&A, management, reglementari, brevete, capital, juridic).
Context de piata: VIX si S&P 500 fata de SMA200. Totul ca dict serializabil, pentru cache-ul lentilelor.
"""
import math
import re
import time

import pandas as pd

from userctx import UPath

RATING_DAYS = 90
INSIDER_DAYS = 182
NEWS_DAYS = 30
EVENT_DAYS = 180
EVENT_BALANCE_DAYS = 90
MAX_EVENTS = 40
SEC_TIMEOUT = 20
SEC_TICKERS_FILE = UPath("sec_tickers.json", shared=True)
SEC_TICKERS_REFRESH = 7 * 86400
INSIDER_MIN_SALE = 0.01   # vanzarile sub 0,01% din capitalizare (de rutina) nu apar in cronologie

# 8-K: item -> (categorie, ton, alerta)
ITEMS_8K = {
    "1.01": ("agreement", 0, False), "1.02": ("agreement", -1, True), "1.03": ("legal", -1, True),
    "2.01": ("m_and_a", 0, True), "2.05": ("restructuring", -1, True), "2.06": ("impairment", -1, True),
    "3.01": ("listing", -1, True), "4.01": ("auditor", -1, True), "4.02": ("restatement", -1, True),
    "5.01": ("m_and_a", 0, True), "5.02": ("management", 0, True),
}

# categoria unui titlu (prima potrivire castiga) si cuvintele care dau tonul
CATEGORIES = [
    ("m_and_a", r"\b(acquires|acquired|acquisition|merger|merge[sd]?|takeover|buyout|divest\w*|spin-?off|bid for|"
                r"to acquire|(agrees?|agreed|deal|plans?|offer|move) to buy)\b"),
    ("legal", r"\b(lawsuit|sued|sues|class action|settle\w*|verdict|court|jury)\b"),
    # inainte de reglementari: "board approves buyback" e o decizie de capital, nu o aprobare a autoritatilor
    ("capital", r"\b(buyback|repurchase|stock split|share offering|secondary offering|"
                r"(raises|hikes|cuts|slashes|suspends|increases|boosts) (its |the )?(quarterly )?dividend|"
                r"dividend (hike|increase|cut))\b"),
    ("regulation", r"\b(fda|antitrust|regulator\w*|probe|investigation|doj|ftc|sec charges|european commission|"
                   r"ban|tariff\w*|sanction\w*|approval|approves|approved|clearance)\b"),
    ("patents", r"\b(patents?|infring\w*|licens\w*)\b"),
    # o schimbare in conducere, nu orice titlu care pomeneste CEO-ul
    ("management", r"\b((ceo|cfo|coo|chief executive|chief financial|chairman|president)\b.*\b(steps down|step down|"
                   r"resign\w*|retir\w*|depart\w*|ousted|fired|exit\w*|to succeed|successor)|"
                   r"(names|named|appoints?|appointed|hires|taps) .*\b(ceo|cfo|coo|chief|chairman|president))\b"),
    ("earnings", r"\b(earnings|quarterly|q[1-4]|results|revenue|eps|guidance|outlook|forecast)\b"),
]
POSITIVE = (r"\b(beat|beats|tops?|surg\w*|soar\w*|jump\w*|rall\w*|record|upgrade[sd]?|raises?|raised|boost\w*|"
            r"wins?|approv\w*|strong|outperform\w*|bullish|gains?|rebound\w*|exceed\w*)\b")
NEGATIVE = (r"\b(miss|misses|missed|plung\w*|slump\w*|falls?|fell|drops?|dropped|sinks?|tumbl\w*|downgrade[sd]?|"
            r"cuts?|lowers?|lowered|warns?|warning|lawsuit|sued|probe|investigat\w*|recall\w*|layoffs?|fined?|weak\w*|"
            r"bearish|delay\w*|halt\w*|bans?|slashe?s?|losses|plummet\w*|crash\w*)\b")


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _ts(v):
    """Data ca Timestamp fara fus orar (sau None)."""
    try:
        t = pd.Timestamp(v)
    except Exception:
        return None
    if t is pd.NaT:
        return None
    return t.tz_convert(None) if t.tzinfo else t


def _local_day(v):
    """Ziua calendaristica locala (ora bursei), fara fus orar."""
    t = pd.Timestamp(v)
    return (t.tz_localize(None) if t.tzinfo else t).normalize()


def _day(t):
    return t.strftime("%Y-%m-%d")


def classify_headline(title):
    """(categorie sau None, ton -1/0/1) dupa cuvinte-cheie. Titlurile sunt in engleza."""
    s = (title or "").lower()
    cat = next((c for c, rx in CATEGORIES if re.search(rx, s)), None)
    pos, neg = len(re.findall(POSITIVE, s)), len(re.findall(NEGATIVE, s))
    return cat, (pos > neg) - (neg > pos)


def _event(date, source, kind, tone, title, link=None, alert=False):
    return {"id": "%s:%s:%s" % (source, date, title[:60]), "date": date, "source": source, "kind": kind,
            "tone": tone, "title": title, "link": link, "alert": alert}


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------
def rating_stats(df, now, days=RATING_DAYS):
    """upgrades_downgrades din yfinance -> numaratori pe ultimele `days` zile + evenimentele up/down."""
    out = {"upgrades": 0, "downgrades": 0, "raises": 0, "lowers": 0, "events": []}
    if not isinstance(df, pd.DataFrame) or df.empty:
        return out
    cutoff = pd.Timestamp(now, unit="s") - pd.Timedelta(days=days)
    for idx, r in df.iterrows():
        t = _ts(idx)
        if t is None or t < cutoff:
            continue
        action, pta = str(r.get("Action") or "").lower(), str(r.get("priceTargetAction") or "").lower()
        if pta == "raises":
            out["raises"] += 1
        elif pta == "lowers":
            out["lowers"] += 1
        if action in ("up", "down"):
            out["upgrades" if action == "up" else "downgrades"] += 1
            out["events"].append(_event(
                _day(t), "rating", "upgrade" if action == "up" else "downgrade", 1 if action == "up" else -1,
                "%s: %s → %s" % (r.get("Firm") or "?", r.get("FromGrade") or "?", r.get("ToGrade") or "?"),
                alert=action == "down"))
    return out


def insider_stats(df, market_cap, now, days=INSIDER_DAYS):
    """Cumparari si vanzari pe piata ale insiderilor (granturile, cadourile, exercitarile nu conteaza).
    insider_net = (cumparari - vanzari) ca % din capitalizare."""
    out = {"insider_net": None, "insider_buys": 0, "insider_sells": 0, "events": []}
    if not isinstance(df, pd.DataFrame) or df.empty:
        return out
    cutoff = pd.Timestamp(now, unit="s") - pd.Timedelta(days=days)
    buy = sell = 0.0
    seen = False
    for _, r in df.iterrows():
        t = _ts(r.get("Start Date"))
        text = str(r.get("Text") or "")
        if t is None or t < cutoff:
            continue
        value = _num(r.get("Value")) or 0.0
        who = "%s (%s)" % (r.get("Insider") or "?", r.get("Position") or "?")
        if text.startswith("Purchase"):
            seen, buy = True, buy + value
            out["insider_buys"] += 1
            out["events"].append(_event(_day(t), "insider", "insider_buy", 1, "%s: %s" % (who, text), alert=True))
        elif text.startswith("Sale"):
            seen, sell = True, sell + value
            out["insider_sells"] += 1
            if market_cap and value / market_cap * 100 >= INSIDER_MIN_SALE:
                out["events"].append(_event(_day(t), "insider", "insider_sale", 0, "%s: %s" % (who, text)))
    if seen and market_cap:
        out["insider_net"] = (buy - sell) / market_cap * 100
    return out


def institutions_change(df):
    """Schimbarea medie a detinerilor marilor institutii (ponderata cu cat detin), in %."""
    if not isinstance(df, pd.DataFrame) or df.empty or "pctChange" not in df.columns:
        return None
    w = pd.to_numeric(df.get("pctHeld"), errors="coerce")
    c = pd.to_numeric(df["pctChange"], errors="coerce")
    ok = w.notna() & c.notna() & (w > 0)
    if ok.sum() < 3:
        return None
    return float((w[ok] * c[ok]).sum() / w[ok].sum() * 100)


def news_items(raw, now, days=NEWS_DAYS, symbol=None):
    """Rezultatele cautarii Yahoo -> [{date, title, link, publisher, kind, tone}] din ultimele `days` zile.
    Cautarea intoarce si articole generale; cand Yahoo da tickerele legate, se pastreaza doar cele cu simbolul cautat."""
    out = []
    for n in raw or []:
        related = n.get("relatedTickers")
        if symbol and related and symbol.upper() not in {str(x).upper() for x in related}:
            continue
        title = str(n.get("title") or "").strip()
        ts = _num(n.get("providerPublishTime"))
        if not title or ts is None or now - ts > days * 86400:
            continue
        cat, tone = classify_headline(title)
        out.append({"date": time.strftime("%Y-%m-%d", time.gmtime(ts)), "title": title, "link": n.get("link"),
                    "publisher": n.get("publisher"), "kind": cat, "tone": tone})
    return out


def news_tone(items):
    """(pozitive - negative) / (pozitive + negative) * 100; minim trei titluri cu ton."""
    pos = sum(1 for i in items if i["tone"] > 0)
    neg = sum(1 for i in items if i["tone"] < 0)
    return (pos - neg) / (pos + neg) * 100 if pos + neg >= 3 else None


# ---------------------------------------------------------------------------
# Evenimente
# ---------------------------------------------------------------------------
def earnings_stats(earn, close, now):
    """earnings_dates + preturile zilnice -> rata de surprize pozitive (8 trimestre), surpriza si reactia medie (4).
    Reactia: raportare dupa inchidere -> ziua urmatoare fata de ziua raportarii; inainte de deschidere -> ziua
    raportarii fata de ziua anterioara."""
    out = {"beat_rate": None, "avg_surprise": None, "avg_reaction": None, "earnings_n": 0, "events": []}
    if not isinstance(earn, pd.DataFrame) or earn.empty or "Reported EPS" not in earn.columns:
        return out
    rows = []
    for idx, r in earn.iterrows():
        rep, est = _num(r.get("Reported EPS")), _num(r.get("EPS Estimate"))
        if rep is None:
            continue
        sur = _num(r.get("Surprise(%)"))
        if sur is None and est:
            sur = (rep / est - 1) * 100 if est > 0 else None
        rows.append((pd.Timestamp(idx), rep, est, sur))
    rows.sort(key=lambda x: x[0], reverse=True)
    if not rows:
        return out
    s = None
    if close is not None and len(close):
        s = pd.Series(list(close.values), index=pd.DatetimeIndex([_local_day(i) for i in close.index])).dropna()
    reacts = []
    for when, rep, est, sur in rows[:8]:
        day, hour = _local_day(when), when.hour
        react = None
        if s is not None:
            before = s[s.index < day] if hour < 12 else s[s.index <= day]
            after = s[s.index >= day] if hour < 12 else s[s.index > day]
            if len(before) and len(after) and (after.index[0] - before.index[-1]).days <= 5:
                react = float((after.iloc[0] / before.iloc[-1] - 1) * 100)
        reacts.append(react)
        if now - day.timestamp() <= EVENT_DAYS * 86400:
            title = "EPS %.2f vs %s%s%s" % (rep, "%.2f" % est if est is not None else "n/a",
                                            " (%+.1f%%)" % sur if sur is not None else "",
                                            " · %+.1f%%" % react if react is not None else "")
            out["events"].append(_event(_day(day), "earnings", "earnings",
                                        (sur > 0) - (sur < 0) if sur is not None else 0, title))
    surs = [r[3] for r in rows[:8] if r[3] is not None]
    out["earnings_n"] = len(surs)
    if len(surs) >= 4:
        out["beat_rate"] = sum(1 for x in surs if x > 0) / len(surs) * 100
        out["avg_surprise"] = sum(surs[:4]) / 4
    r4 = [x for x in reacts[:4] if x is not None]
    if len(r4) >= 3:
        out["avg_reaction"] = sum(r4) / len(r4)
    return out


def sec_headers(ua_email):
    return {"User-Agent": "GoldRetriever %s" % ua_email, "Accept-Encoding": "gzip, deflate"}


def sec_cik(symbol, ua_email, now=None, get=None):
    """CIK-ul SEC al unui ticker american; lista SEC se tine local o saptamana."""
    from core import load_json_file, save_json_file
    now = now or time.time()
    cached = load_json_file(SEC_TICKERS_FILE, {})
    if not cached.get("map") or now - float(cached.get("fetched_at") or 0) >= SEC_TICKERS_REFRESH:
        import requests
        get = get or requests.get
        r = get("https://www.sec.gov/files/company_tickers.json", headers=sec_headers(ua_email), timeout=SEC_TIMEOUT)
        if r.status_code != 200:
            return None
        cached = {"fetched_at": now, "map": {str(v["ticker"]).upper(): int(v["cik_str"]) for v in r.json().values()}}
        save_json_file(SEC_TICKERS_FILE, cached)
    return cached["map"].get(symbol.upper().replace(".", "-"))


def parse_8k(submissions, cik, now, days=EVENT_DAYS):
    """submissions JSON (data.sec.gov) -> evenimente din rapoartele 8-K, pe iteme."""
    rec = (submissions or {}).get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form != "8-K":
            continue
        date = rec["filingDate"][i]
        t = _ts(date)
        if t is None or now - t.timestamp() > days * 86400:
            continue
        acc = rec["accessionNumber"][i]
        link = "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (cik, acc.replace("-", ""), rec["primaryDocument"][i])
        for item in str(rec["items"][i] or "").split(","):
            item = item.strip()
            if item in ITEMS_8K:
                kind, tone, alert = ITEMS_8K[item]
                out.append(_event(date, "sec", kind, tone, "8-K %s" % item, link, alert))
    return out


def edgar_events(symbol, ua_email, now, get=None):
    import health
    import requests
    get = get or requests.get
    with health.timed("sec") as h:
        cik = sec_cik(symbol, ua_email, now, get)
        if not cik:
            return []
        r = get("https://data.sec.gov/submissions/CIK%010d.json" % cik, headers=sec_headers(ua_email), timeout=SEC_TIMEOUT)
        if r.status_code != 200:
            h.ok, h.error = False, "HTTP %s" % r.status_code
            return []
        return parse_8k(r.json(), cik, now)


def event_balance(events, now, days=EVENT_BALANCE_DAYS):
    """Suma tonurilor catalizatorilor din ultimele `days` zile (8-K, stiri clasificate, cumparari de insideri).
    Ratingurile si earnings au indicatorii lor, deci nu intra aici."""
    total, n = 0, 0
    for e in events:
        if e["source"] in ("rating", "earnings") or e.get("kind") in (None, "earnings"):
            continue
        t = _ts(e["date"])
        if t is not None and now - t.timestamp() <= days * 86400:
            total += e["tone"]
            n += 1
    return total, n


# ---------------------------------------------------------------------------
# Toate datele unui ticker
# ---------------------------------------------------------------------------
def extract(tk, symbol, info, now=None, ua_email=None, news_fn=None, edgar_fn=None):
    """Metricile pentru Sentiment si Evenimente + cronologia evenimentelor (cele mai noi primele)."""
    now = now or time.time()

    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    m = {}
    ratings = rating_stats(safe(lambda: tk.upgrades_downgrades), now)
    m.update({k: ratings[k] for k in ("upgrades", "downgrades", "raises", "lowers")})
    m["rating_net_90d"] = ratings["upgrades"] - ratings["downgrades"]
    n_t = ratings["raises"] + ratings["lowers"]
    m["target_net_90d"] = (ratings["raises"] - ratings["lowers"]) / n_t * 100 if n_t >= 3 else None
    rec, n_an = _num(info.get("recommendationMean")), _num(info.get("numberOfAnalystOpinions")) or 0
    m["rec_mean"] = rec if rec and n_an >= 3 else None
    m["analysts_n"] = int(n_an)
    sf = _num(info.get("shortPercentOfFloat"))
    m["short_float"] = sf * 100 if sf is not None else None
    sh, prior = _num(info.get("sharesShort")), _num(info.get("sharesShortPriorMonth"))
    m["short_change"] = (sh / prior - 1) * 100 if sh is not None and prior else None
    ins = insider_stats(safe(lambda: tk.insider_transactions), _num(info.get("marketCap")), now)
    m.update({k: ins[k] for k in ("insider_net", "insider_buys", "insider_sells")})
    m["inst_change"] = institutions_change(safe(lambda: tk.institutional_holders))

    news = news_items((news_fn or fetch_news)(symbol), now, symbol=symbol)
    m["news_tone"] = news_tone(news)
    m["news_n"] = len(news)

    close = safe(lambda: tk.history(period="2y")["Close"])
    earn = earnings_stats(safe(lambda: tk.get_earnings_dates(limit=12)), close, now)
    m.update({k: earn[k] for k in ("beat_rate", "avg_surprise", "avg_reaction", "earnings_n")})

    sec = []
    if ua_email and "." not in symbol and info.get("country") == "United States":
        sec = safe(lambda: (edgar_fn or edgar_events)(symbol, ua_email, now)) or []
    m["sec_checked"] = bool(ua_email and "." not in symbol and info.get("country") == "United States")

    news_events = [_event(n["date"], "news", n["kind"], n["tone"], n["title"], n["link"])
                   for n in news if n["kind"] not in (None, "earnings")]
    events = ratings["events"] + ins["events"] + earn["events"] + sec + news_events
    events.sort(key=lambda e: e["date"], reverse=True)
    m["events"] = events[:MAX_EVENTS]
    m["event_balance"], m["event_n"] = event_balance(m["events"], now)
    if not m["event_n"]:
        m["event_balance"] = None
    return m


def fetch_news(symbol, count=20):
    from yf_compat import yf, YFINANCE_AVAILABLE
    if not YFINANCE_AVAILABLE:
        return []
    try:
        return yf.Search(symbol, news_count=count, max_results=1, enable_fuzzy_query=False).news or []
    except Exception:
        return []


def market_context():
    """VIX si distanta S&P 500 fata de media pe 200 de zile (%). Nu intra in scoruri, e contextul pietei."""
    from yf_compat import yf, YFINANCE_AVAILABLE
    out = {"vix": None, "spx_vs_sma200": None}
    if not YFINANCE_AVAILABLE:
        return out
    try:
        out["vix"] = float(yf.Ticker("^VIX").history(period="5d")["Close"].dropna().iloc[-1])
    except Exception:
        pass
    try:
        c = yf.Ticker("^GSPC").history(period="1y")["Close"].dropna()
        if len(c) >= 200:
            out["spx_vs_sma200"] = float((c.iloc[-1] / c.iloc[-200:].mean() - 1) * 100)
    except Exception:
        pass
    return out


def ua_email():
    """Adresa de contact pentru SEC (cerinta lor de User-Agent): emailul primului admin. Fara ea, EDGAR nu se foloseste."""
    try:
        import notify
        found = notify.recipients()
        return found[0] if found else None
    except Exception:
        return None
