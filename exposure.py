"""Expunerea portofoliului pe sector, tara si moneda.

Actiuni: sectorul si tara din Yahoo. ETF-uri: defalcarea pe sectoare din Yahoo si pe tari din justETF (dupa ISIN),
ambele look-through; ETF-urile fara date raman intr-o categorie separata. Moneda: moneda de tranzactionare.
"""
import threading
import time

from core import load_json_file, read_status, save_json_file, update_json_file
from userctx import UPath

EXPOSURE_CACHE_FILE = UPath("exposure_cache.json", shared=True)
EXPOSURE_STATUS_FILE = UPath("exposure_status.json", shared=True)
EXPOSURE_REFRESH_INTERVAL = 7 * 86400
COUNTRIES_RETRY = 86400  # justETF indisponibil sau ISIN negasit: reincercare dupa o zi

DIMENSIONS = ("sector", "country", "currency")
# chei din funds_data.sector_weightings -> numele de sector folosite la actiuni
ETF_SECTORS = {
    "realestate": "Real Estate", "consumer_cyclical": "Consumer Cyclical", "basic_materials": "Basic Materials",
    "consumer_defensive": "Consumer Defensive", "technology": "Technology",
    "communication_services": "Communication Services", "financial_services": "Financial Services",
    "utilities": "Utilities", "industrials": "Industrials", "energy": "Energy", "healthcare": "Healthcare",
}
ETF = "_etf"            # ETF fara defalcare pe tari
UNKNOWN = "_unknown"
OTHER = "_other"        # restul ponderilor ETF (cash, obligatiuni etc.)


def parse_meta(info, sector_weights=None):
    """info si sector_weightings din yfinance -> {kind, sector, country, sectors}."""
    info = info or {}
    quote = str(info.get("quoteType") or "").upper()
    kind = "etf" if quote in ("ETF", "MUTUALFUND") or sector_weights else "stock" if quote == "EQUITY" else "other"
    sectors = {}
    for k, w in (sector_weights or {}).items():
        try:
            w = float(w)
        except (TypeError, ValueError):
            continue
        if w > 0:
            name = ETF_SECTORS.get(k, k)
            sectors[name] = sectors.get(name, 0.0) + w
    return {"kind": kind, "sector": info.get("sector"), "country": info.get("country"), "sectors": sectors}


def _spread(add, value, weights):
    """Imparte valoarea dupa ponderi (fractii); ce lipseste pana la 100% merge la OTHER."""
    total = sum(weights.values())
    for k, w in weights.items():
        add(k, value * w / max(total, 1.0))
    if total < 0.999:
        add(OTHER, value * (1 - total))


def parse_countries(items):
    """Lista justETF [{name, percentage}] -> {tara: fractie}; "Other" devine OTHER."""
    out = {}
    for it in items or []:
        try:
            w = float(it.get("percentage")) / 100
        except (TypeError, ValueError, AttributeError):
            continue
        name = str(it.get("name") or "").strip()
        if w > 0 and name:
            key = OTHER if name.lower() == "other" else name
            out[key] = out.get(key, 0.0) + w
    return out


def fetch_countries(isin):
    """Tarile unui ETF din justETF. Varianta extinsa (lista completa) intoarce uneori o lista goala cand
    pagina nu are "load more"; atunci se reincearca fara extindere."""
    try:
        import justetf_scraping
    except ImportError:
        return None
    for expand in (True, False):
        try:
            o = justetf_scraping.get_etf_overview(isin, include_gettex=False, expand_allocations=expand)
        except Exception as e:
            print(f"[exposure] justETF {isin}: {str(e)[:120]}", flush=True)
            return None
        countries = parse_countries(o.get("countries"))
        if countries:
            return countries
    return {}


def breakdown(rows, meta, dim):
    """rows: [{ticker, value, currency}]. Intoarce [(categorie, valoare, %)] descrescator."""
    out = {}

    def add(key, v):
        out[key] = out.get(key, 0.0) + v

    for r in rows:
        v = r.get("value")
        if not v or v <= 0:
            continue
        m = meta.get(r["ticker"]) or {}
        if dim == "currency":
            add(r.get("currency") or UNKNOWN, v)
        elif dim == "country" and m.get("countries"):
            _spread(add, v, m["countries"])
        elif dim == "country":
            add(m.get("country") or (ETF if m.get("kind") == "etf" else UNKNOWN), v)
        elif m.get("sectors"):
            _spread(add, v, m["sectors"])
        else:
            add(m.get("sector") or (ETF if m.get("kind") == "etf" else UNKNOWN), v)
    grand = sum(out.values())
    if not grand:
        return []
    return sorted(((k, v, v / grand * 100) for k, v in out.items()), key=lambda x: -x[1])


def fetch_meta(yahoo_symbol):
    from yf_compat import yf, YFINANCE_AVAILABLE
    if not YFINANCE_AVAILABLE:
        return None, "yfinance indisponibil"
    try:
        tk = yf.Ticker(yahoo_symbol)
        info = tk.info or {}
        weights = None
        if str(info.get("quoteType") or "").upper() in ("ETF", "MUTUALFUND"):
            try:
                weights = tk.funds_data.sector_weightings
            except Exception:
                weights = None
        return parse_meta(info, weights), None
    except Exception as e:
        return None, str(e)[:200]


def load_cache():
    return load_json_file(EXPOSURE_CACHE_FILE, {})


def load_status():
    return read_status(EXPOSURE_STATUS_FILE)


def _stale(entry, isin, now):
    if entry.get("fetched_at") is None or now - float(entry["fetched_at"]) >= EXPOSURE_REFRESH_INTERVAL:
        return True
    if entry.get("kind") != "etf" or not isin:
        return False
    # intrari de dinainte de tarile din justETF (inca necautate) sau cu eroare mai veche de o zi
    if "countries" not in entry:
        return True
    return bool(entry.get("countries_error")) and now - float(entry["fetched_at"]) >= COUNTRIES_RETRY


def fetch_and_cache(tickers, resolve=None, now=None, sleep=1.0, isins=None, countries_fn=None):
    """Actualizeaza metadatele tickerelor lipsa sau mai vechi de o saptamana. isins: {ticker: ISIN}, pentru tarile ETF."""
    if resolve is None:
        from yahoo import resolve_yahoo_symbol as resolve
    countries_fn = countries_fn or fetch_countries
    isins = isins or {}
    now = now if now is not None else time.time()
    cache = load_cache()
    todo = [t for t in tickers if _stale(cache.get(t) or {}, isins.get(t), now)]
    total = len(todo)
    save_json_file(EXPOSURE_STATUS_FILE, {"in_progress": True, "started_at": now, "total": total, "done": 0})
    try:
        for idx, ticker in enumerate(todo):
            symbol = resolve(ticker)
            meta, err = fetch_meta(symbol)
            entry = dict(meta or {"kind": "other", "sector": None, "country": None, "sectors": {}},
                         symbol=symbol, fetched_at=now)
            if err:
                entry["error"] = err
            if entry.get("kind") == "etf" and isins.get(ticker):
                countries = countries_fn(isins[ticker])
                entry["countries"] = countries or {}
                if countries is None:
                    entry["countries_error"] = True
            cache[ticker] = entry
            update_json_file(EXPOSURE_CACHE_FILE, {}, lambda c, t=ticker: dict(c, **{t: cache[t]}))
            save_json_file(EXPOSURE_STATUS_FILE, {"in_progress": True, "started_at": None, "total": total, "done": idx + 1})
            if sleep and idx < total - 1:
                time.sleep(sleep)
    finally:
        save_json_file(EXPOSURE_STATUS_FILE, {"in_progress": False, "started_at": None, "total": total, "done": total})
    return cache


def start_fetch_background(tickers, isins=None):
    if load_status().get("in_progress"):
        return False
    threading.Thread(target=fetch_and_cache, args=(list(tickers),), kwargs={"isins": dict(isins or {})},
                     daemon=True).start()
    return True
