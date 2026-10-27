import re
import threading
import time
from datetime import date, datetime

from core import (
    WATCHLIST_CACHE_FILE,
    WATCHLIST_FILE,
    WATCHLIST_PRICES_REFRESH_INTERVAL,
    WATCHLIST_REFRESH_INTERVAL,
    WATCHLIST_STATUS_FILE,
    load_json_file,
    read_status,
    save_json_file,
    update_json_file,
)
from etf import compute_etf_score, extract_etf_metrics
from risk import compute_risk, extract_risk_metrics
from scoring import compute_score, extract_metrics
from yf_compat import YFINANCE_AVAILABLE, yf


def load_watchlist():
    watchlist = load_json_file(WATCHLIST_FILE, [])
    return watchlist if isinstance(watchlist, list) else []


def load_watchlist_cache():
    cache = load_json_file(WATCHLIST_CACHE_FILE, {})
    return cache if isinstance(cache, dict) else {}


def _get_fast_info_value(fast_info, key):
    if fast_info is None:
        return None
    if isinstance(fast_info, dict):
        return fast_info.get(key)
    try:
        return fast_info.get(key)
    except Exception:
        return getattr(fast_info, key, None)


def compute_watch_entry(symbol, isin=None):
    entry = {
        "name": symbol,
        "currency": None,
        "price": None,
        "quality_total": None,
        "quality_rating": None,
        "quality_coverage": None,
        "risk_total": None,
        "risk_rating": None,
        "risk_coverage": None,
        "updated": datetime.now().isoformat(),
    }

    if not YFINANCE_AVAILABLE:
        return entry

    tk = yf.Ticker(symbol)
    metrics = None
    quote_type = None

    try:
        info = tk.info or {}
        quote_type = info.get("quoteType")
        entry["name"] = info.get("shortName") or symbol
    except Exception:
        entry["name"] = symbol

    if not isin and quote_type in {"ETF", "MUTUALFUND"}:
        entry["kind"] = "etf_no_isin"

    try:
        entry["currency"] = _get_fast_info_value(getattr(tk, "fast_info", None), "currency")
    except Exception:
        entry["currency"] = None

    try:
        history = tk.history(period="5d")
        if history is not None and not history.empty and "Close" in history:
            close = history["Close"].dropna()
            if not close.empty:
                entry["price"] = round(float(close.iloc[-1]), 2)
    except Exception:
        entry["price"] = None

    try:
        if isin:
            em, labels, notes = extract_etf_metrics(isin, symbol)
            er = compute_etf_score(em)
            entry["kind"] = "etf"
            entry["etf_labels"] = labels
            if entry["name"] == symbol and labels.get("nume"):
                entry["name"] = labels["nume"]
            entry["quality_total"] = er.get("total")
            entry["quality_rating"] = er.get("rating")
            entry["quality_coverage"] = er.get("coverage")
            metrics = {}
        else:
            metrics, _ = extract_metrics(tk)
            quality = compute_score(metrics)
            entry["quality_total"] = quality.get("total")
            entry["quality_rating"] = quality.get("rating")
            entry["quality_coverage"] = quality.get("coverage")
    except Exception:
        metrics = None

    try:
        risk_metrics, _ = extract_risk_metrics(tk, metrics)
        risk = compute_risk(risk_metrics)
        entry["risk_total"] = risk.get("total")
        entry["risk_rating"] = risk.get("rating")
        entry["risk_coverage"] = risk.get("coverage")
    except Exception:
        pass

    entry["updated"] = datetime.now().isoformat()
    return entry


def add_to_watchlist(symbol, isin=None):
    if not YFINANCE_AVAILABLE:
        return False, "Yahoo Finance indisponibil"

    symbol = symbol.strip().upper()
    if not symbol:
        return False, "Simbolul este obligatoriu"
    if any(ch.isspace() for ch in symbol):
        return False, "Simbolul nu poate conține spații"
    if len(symbol) > 15:
        return False, "Simbolul este prea lung"

    isin = isin.strip().upper() if isinstance(isin, str) else isin
    isin = isin or None
    if isin is not None and not re.fullmatch(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", isin):
        return False, "ISIN invalid"

    watchlist = load_watchlist()
    existing_item = next(
        (
            item for item in watchlist
            if isinstance(item, dict) and item.get("symbol") == symbol
        ),
        None,
    )
    if existing_item is not None:
        if isin and not existing_item.get("isin"):
            def isin_updater(items):
                items = list(items or [])
                for item in items:
                    if isinstance(item, dict) and item.get("symbol") == symbol and not item.get("isin"):
                        item["isin"] = isin
                        break
                return items

            update_json_file(WATCHLIST_FILE, [], isin_updater)

            cache = load_watchlist_cache()
            cache[symbol] = compute_watch_entry(symbol, isin)
            save_json_file(WATCHLIST_CACHE_FILE, cache)

            return True, f"ISIN adăugat pentru {symbol}"

        return False, f"{symbol} există deja în watchlist"

    try:
        history = yf.Ticker(symbol).history(period="5d")
        if history is None or history.empty:
            return False, "Simbolul nu are date pe Yahoo Finance"
    except Exception:
        return False, "Simbolul nu are date pe Yahoo Finance"

    entry = compute_watch_entry(symbol, isin)

    cache = load_watchlist_cache()
    cache[symbol] = entry
    save_json_file(WATCHLIST_CACHE_FILE, cache)

    def updater(items):
        items = list(items or [])
        if not any(item.get("symbol") == symbol for item in items if isinstance(item, dict)):
            items.append({
                "symbol": symbol,
                "name": entry.get("name") or symbol,
                "added": date.today().isoformat(),
                "isin": isin,
            })
        return items

    update_json_file(WATCHLIST_FILE, [], updater)
    return True, f"{symbol} adăugat"


def remove_from_watchlist(symbol):
    symbol = symbol.strip().upper()

    def watchlist_updater(items):
        return [
            item for item in list(items or [])
            if not isinstance(item, dict) or item.get("symbol") != symbol
        ]

    update_json_file(WATCHLIST_FILE, [], watchlist_updater)

    def cache_updater(cache):
        cache = dict(cache or {})
        cache.pop(symbol, None)
        return cache

    update_json_file(WATCHLIST_CACHE_FILE, {}, cache_updater)


def _is_cache_entry_stale(entry, now):
    if not entry or not entry.get("updated"):
        return True
    try:
        updated = datetime.fromisoformat(entry["updated"])
        return (now - updated).total_seconds() >= WATCHLIST_REFRESH_INTERVAL
    except Exception:
        return True


def fetch_and_cache_watchlist(force=False):
    watchlist = load_watchlist()
    total = len(watchlist)
    save_json_file(WATCHLIST_STATUS_FILE, {
        "in_progress": True,
        "started_at": time.time(),
        "total": total,
        "done": 0,
    })

    cache = load_watchlist_cache()
    now = datetime.now()

    for idx, item in enumerate(watchlist):
        symbol = item.get("symbol") if isinstance(item, dict) else None
        isin = item.get("isin") if isinstance(item, dict) else None
        try:
            if not symbol:
                continue

            symbol = symbol.strip().upper()
            cached_entry = cache.get(symbol)
            if force or _is_cache_entry_stale(cached_entry, now):
                cache[symbol] = compute_watch_entry(symbol, isin)
                save_json_file(WATCHLIST_CACHE_FILE, cache)
        except Exception as e:
            print(f"[watchlist] {symbol}: {e}", flush=True)
        finally:
            save_json_file(WATCHLIST_STATUS_FILE, {
                "in_progress": True,
                "started_at": None,
                "total": total,
                "done": idx + 1,
            })
            if idx < total - 1:
                time.sleep(1)

    save_json_file(WATCHLIST_STATUS_FILE, {
        "in_progress": False,
        "started_at": None,
        "total": total,
        "done": total,
    })
    return cache


def fetch_last_prices(symbols):
    """Ultimul pret de inchidere pentru toate simbolurile, intr-o singura cerere Yahoo."""
    import pandas as pd
    data = yf.download(symbols, period="5d", progress=False, group_by="ticker", auto_adjust=False, threads=False)
    prices = {}
    if data is None or data.empty:
        return prices
    for symbol in symbols:
        try:
            frame = data[symbol] if isinstance(data.columns, pd.MultiIndex) else data
            close = frame["Close"].dropna()
            if not close.empty:
                prices[symbol] = round(float(close.iloc[-1]), 2)
        except Exception:
            continue
    return prices


def refresh_watchlist_prices():
    """Actualizeaza doar pretul (si price_updated) intre doua recalculari complete; "updated" ramane al
    recalcularii zilnice, care decide cand se recalculeaza scorurile. Simbolurile noi raman pe calculul complet."""
    if not YFINANCE_AVAILABLE or read_status(WATCHLIST_STATUS_FILE).get("in_progress"):
        return {}
    symbols = sorted({str(i.get("symbol")).strip().upper() for i in load_watchlist() if isinstance(i, dict) and i.get("symbol")})
    if not symbols:
        return {}
    try:
        prices = fetch_last_prices(symbols)
    except Exception as e:
        print(f"[watchlist] price refresh failed: {e}", flush=True)
        return {}
    if not prices:
        return {}
    stamp = datetime.now().isoformat()

    def updater(cache):
        cache = dict(cache) if isinstance(cache, dict) else {}
        for symbol, price in prices.items():
            if isinstance(cache.get(symbol), dict):
                cache[symbol] = dict(cache[symbol], price=price, price_updated=stamp)
        return cache

    update_json_file(WATCHLIST_CACHE_FILE, {}, updater)
    return prices


_prices_running = threading.Lock()


def start_watchlist_prices_background():
    if not _prices_running.acquire(blocking=False):
        return False

    def run():
        try:
            refresh_watchlist_prices()
        finally:
            _prices_running.release()

    threading.Thread(target=run, daemon=True).start()
    return True


def start_watchlist_refresh_background(force=False):
    status = read_status(WATCHLIST_STATUS_FILE)
    if status.get("in_progress"):
        return False

    thread = threading.Thread(target=fetch_and_cache_watchlist, args=(force,), daemon=True)
    thread.start()
    return True
