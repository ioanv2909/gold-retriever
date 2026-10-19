from datetime import datetime
import threading
import time

from core import (
    XTB_PRICES_FILE,
    XTB_PRICES_STATUS_FILE,
    load_json_file,
    load_ticker_map,
    read_status,
    save_json_file,
    save_ticker_map,
)
from t212_api import fetch_fx_rate
from xtb import load_xtb
from yahoo import resolve_yahoo_symbol
from yf_compat import YFINANCE_AVAILABLE, yf


_DEFAULT_CACHE = {"fetched_at": None, "data": {}}


def normalize_quote(price, currency):
    if currency in {"GBp", "GBX"}:
        return (None if price is None else price / 100), "GBP"
    return price, currency


def check_symbol(ticker, group, account_currency):
    updated = datetime.now().isoformat(timespec="seconds")
    result = {
        "symbol": None,
        "price": None,
        "currency": None,
        "xtb_ref": None,
        "ratio": None,
        "status": "no_data",
        "currency_ok": None,
        "updated": updated,
    }

    try:
        symbol = resolve_yahoo_symbol(ticker)
        result["symbol"] = symbol

        if not YFINANCE_AVAILABLE or not symbol:
            return result

        tk = yf.Ticker(symbol)
        hist = tk.history(period="5d")
        if hist is not None and not hist.empty and "Close" in hist:
            closes = hist["Close"].dropna()
            if not closes.empty:
                result["price"] = float(closes.iloc[-1])

        result["currency"] = _fast_info_currency(tk)
        result["price"], result["currency"] = normalize_quote(result["price"], result["currency"])
        result["xtb_ref"] = _first_lot_current_price(group)

        if result["price"] is not None and result["xtb_ref"]:
            result["ratio"] = result["price"] / result["xtb_ref"]

        if result["price"] is None or not result["currency"]:
            result["status"] = "no_data"
        elif result["ratio"] is not None and not 0.9 <= result["ratio"] <= 1.1:
            result["status"] = "mismatch"
        else:
            result["status"] = "ok"

        result["currency_ok"] = _currency_ok(group, result["currency"], account_currency)
        return result
    except Exception:
        result["status"] = "no_data"
        return result


def load_xtb_prices():
    return load_json_file(XTB_PRICES_FILE, dict(_DEFAULT_CACHE))


def recheck_ticker(ticker):
    xtb_data = load_xtb()

    for account in (xtb_data.get("accounts") or {}).values():
        account_currency = account.get("currency")
        for group in account.get("positions") or []:
            if group.get("ticker") == ticker:
                result = check_symbol(ticker, group, account_currency)
                cache = load_xtb_prices()
                data = dict(cache.get("data") or {})
                data[ticker] = result
                save_json_file(XTB_PRICES_FILE, {"fetched_at": cache.get("fetched_at"), "data": data})
                return result

    result = {
        "symbol": resolve_yahoo_symbol(ticker),
        "price": None,
        "currency": None,
        "xtb_ref": None,
        "ratio": None,
        "status": "no_data",
        "currency_ok": None,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    cache = load_xtb_prices()
    data = dict(cache.get("data") or {})
    data[ticker] = result
    save_json_file(XTB_PRICES_FILE, {"fetched_at": cache.get("fetched_at"), "data": data})
    return result


def save_symbol_override(ticker, symbol):
    symbol = (symbol or "").strip()
    mapping = load_ticker_map()

    if not symbol:
        if ticker in mapping:
            mapping = dict(mapping)
            mapping.pop(ticker, None)
            save_ticker_map(mapping)
        recheck_ticker(ticker)
        return True, "Suprascriere ștearsă"

    if not YFINANCE_AVAILABLE:
        return False, "Simbolul nu are date pe Yahoo Finance"

    try:
        hist = yf.Ticker(symbol).history(period="5d")
    except Exception:
        hist = None

    if hist is None or hist.empty:
        return False, "Simbolul nu are date pe Yahoo Finance"

    mapping = dict(mapping)
    mapping[ticker] = symbol
    save_ticker_map(mapping)

    result = recheck_ticker(ticker)
    return True, f"Salvat; stare: {result.get('status')}"


def refresh_xtb_prices():
    ticker_groups = _xtb_ticker_groups()
    total = len(ticker_groups)
    cache = load_xtb_prices()
    data = dict(cache.get("data") or {})

    save_json_file(XTB_PRICES_STATUS_FILE, {"in_progress": True, "total": total, "done": 0})

    try:
        for done, (ticker, payload) in enumerate(ticker_groups.items(), start=1):
            try:
                data[ticker] = check_symbol(ticker, payload["group"], payload["account_currency"])
                cache = {"fetched_at": time.time(), "data": data}
                save_json_file(XTB_PRICES_FILE, cache)
            except Exception as e:
                print(f"[xtb_prices] {ticker}: {e}", flush=True)

            save_json_file(XTB_PRICES_STATUS_FILE, {"in_progress": True, "total": total, "done": done})
            time.sleep(0.5)
    finally:
        save_json_file(XTB_PRICES_STATUS_FILE, {"in_progress": False, "total": total, "done": total})


def start_xtb_prices_refresh_background():
    if read_status(XTB_PRICES_STATUS_FILE).get("in_progress"):
        return False

    xtb_data = load_xtb()
    if not (xtb_data.get("accounts") or {}):
        return False

    thread = threading.Thread(target=refresh_xtb_prices, daemon=True)
    thread.start()
    return True


def _xtb_ticker_groups():
    xtb_data = load_xtb()
    ticker_groups = {}

    for account in (xtb_data.get("accounts") or {}).values():
        account_currency = account.get("currency")
        for group in account.get("positions") or []:
            ticker = group.get("ticker")
            if ticker and ticker not in ticker_groups:
                ticker_groups[ticker] = {"group": group, "account_currency": account_currency}

    return ticker_groups


def _fast_info_currency(tk):
    fast_info = getattr(tk, "fast_info", None) or {}
    try:
        return fast_info.get("currency")
    except AttributeError:
        try:
            return fast_info["currency"]
        except Exception:
            return None


def _first_lot_current_price(group):
    for lot in group.get("lots") or []:
        current_price = _to_float(lot.get("current_price"))
        if current_price:
            return current_price
    return None


def _currency_ok(group, currency, account_currency):
    open_price = _to_float(group.get("open_price"))
    volume = _to_float(group.get("volume"))
    value = _to_float(group.get("value"))
    net_profit = _to_float(group.get("net_profit"))

    if not currency or not account_currency or not open_price or not volume or value is None or net_profit is None:
        return None

    denominator = open_price * volume
    if not denominator:
        return None

    cost_account = value - net_profit
    implied_fx = cost_account / denominator
    expected_fx = 1.0 if currency == account_currency else fetch_fx_rate(currency, account_currency)[0]

    if not implied_fx or not expected_fx:
        return None

    return abs(implied_fx / expected_fx - 1) < 0.15


def _to_float(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number
