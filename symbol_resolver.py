"""Simbolul Yahoo corect pentru tickerele la care cel ghicit din tickerul brokerului nu are date
(ex. IITU -> IITU.L, DJGTEEX.DE -> EXI2.DE). Se cauta pe Yahoo dupa simbolul de baza, apoi dupa ISIN,
si se pastreaza doar un simbol care chiar are preturi. Rezultatul e comun tuturor utilizatorilor;
maparea manuala din pagina pozitiei (ticker_map) are mereu prioritate."""
import os
import threading
import time

from core import load_json_file, save_json_file
from userctx import UPath
from yf_compat import yf, YFINANCE_AVAILABLE

AUTO_MAP_FILE = UPath("yahoo_auto_map.json", shared=True)
RECHECK_S = 7 * 86400   # un ticker verificat (gasit sau nu) se reverifica dupa o saptamana
MAX_PER_RUN = 20        # cate tickere noi se verifica intr-un tur (fiecare inseamna cateva cereri Yahoo)

_cache = {"mtime": None, "data": {}}
_running = threading.Lock()


def _load():
    path = os.fspath(AUTO_MAP_FILE)
    try:
        m = os.path.getmtime(path)
    except OSError:
        return {}
    if m != _cache["mtime"]:
        data = load_json_file(path, {})
        _cache.update(mtime=m, data=data if isinstance(data, dict) else {})
    return _cache["data"]


def lookup(ticker):
    """Simbolul gasit automat pentru ticker, sau None (atunci ramane cel ghicit)."""
    entry = _load().get(ticker)
    return entry.get("symbol") if isinstance(entry, dict) else None


def has_prices(symbol):
    try:
        hist = yf.Ticker(symbol).history(period="5d")
        return hist is not None and not hist.empty
    except Exception:
        return False


def _search(query):
    try:
        return [q.get("symbol") for q in (yf.Search(query, max_results=8).quotes or []) if q.get("symbol")]
    except Exception:
        return []


def find_symbol(guess, isin=None):
    """Primul simbol cu preturi: acelasi simbol de baza pe alta bursa, apoi rezultatele cautarii dupa ISIN."""
    base = guess.split(".")[0]
    candidates = [s for s in _search(base) if s.split(".")[0] == base and s != guess]
    if isin:
        candidates += [s for s in _search(isin) if s not in candidates and s != guess]
    for symbol in candidates:
        if has_prices(symbol):
            return symbol
    return None


def fix_symbols(tickers, isins=None, now=None):
    """Verifica tickerele fara mapare manuala; intoarce {ticker: simbol} pentru cele corectate in acest tur."""
    from core import load_ticker_map
    from yahoo import guess_yahoo_symbol
    now = now or time.time()
    isins = isins or {}
    manual = load_ticker_map()
    known = dict(_load())
    fixed, checked = {}, 0
    for ticker in tickers:
        if checked >= MAX_PER_RUN:
            break
        entry = known.get(ticker)
        if ticker in manual or (isinstance(entry, dict) and now - float(entry.get("checked") or 0) < RECHECK_S):
            continue
        checked += 1
        guess = guess_yahoo_symbol(ticker)
        symbol = None
        if not has_prices(guess):
            symbol = find_symbol(guess, isins.get(ticker))
            if symbol:
                fixed[ticker] = symbol
                print(f"[yahoo] symbol {guess} has no data, using {symbol} for {ticker}", flush=True)
            else:
                print(f"[yahoo] symbol {guess} has no data and no alternative was found for {ticker}", flush=True)
        known[ticker] = {"symbol": symbol, "guess": guess, "isin": isins.get(ticker), "checked": now}
    if checked:
        save_json_file(AUTO_MAP_FILE, known)
    return fixed


def start_fix_background(tickers, isins=None):
    if not YFINANCE_AVAILABLE or not _running.acquire(blocking=False):
        return False
    from userctx import current_user, set_user
    user = current_user()  # maparea manuala e per utilizator

    def run():
        try:
            set_user(user)
            fix_symbols(tickers, isins)
        except Exception as e:
            print(f"[yahoo] symbol check failed: {e}", flush=True)
        finally:
            _running.release()

    threading.Thread(target=run, daemon=True).start()
    return True
