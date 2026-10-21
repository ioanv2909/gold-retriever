from datetime import date, timedelta
import streamlit as st
import requests
import pandas as pd
import numpy as np
import base64
import os
import json
import time
import threading
import tempfile
from datetime import datetime
from urllib.parse import quote
import plotly.graph_objects as go
import plotly.express as px



# ---------------------------------------------------------------------------
# Persistență (fișiere pe volum montat: .:/app)
# ---------------------------------------------------------------------------
from userctx import UPath
CONFIG_FILE = UPath("config.json")
INSTRUMENTS_CACHE_FILE = UPath("instruments_cache.json", shared=True)
ACCOUNT_INFO_CACHE_FILE = UPath("account_info_cache.json")
PORTFOLIO_CACHE_FILE = UPath("portfolio_cache.json")
DIVIDENDS_CACHE_FILE = UPath("dividends_cache.json")
DIVIDENDS_STATUS_FILE = UPath("dividends_status.json")
RATINGS_CACHE_FILE = UPath("ratings_cache.json")
RATINGS_STATUS_FILE = UPath("ratings_status.json")
QUALITY_CACHE_FILE = UPath("quality_cache.json", shared=True)
MARKET_CONTEXT_CACHE_FILE = UPath("market_context_cache.json", shared=True)
JUSTETF_CACHE_FILE = UPath("justetf_cache.json", shared=True)
WATCHLIST_FILE = UPath("watchlist.json")
WATCHLIST_CACHE_FILE = UPath("watchlist_cache.json")
WATCHLIST_STATUS_FILE = UPath("watchlist_status.json")
PORTFOLIO_HISTORY_FILE = UPath("portfolio_history.json")
TICKER_MAP_FILE = UPath("ticker_map.json")
NOTES_FILE = UPath("notes.json")
ALERT_STATE_FILE = UPath("alert_state.json")
ALERTS_FILE = UPath("alerts.json")
XTB_FILE = UPath("xtb.json")
XTB_PRICES_FILE = UPath("xtb_prices.json")
XTB_PRICES_STATUS_FILE = UPath("xtb_prices_status.json")
ALERT_MIN_DAYS_HELD = 180

INSTRUMENTS_CACHE_TTL = 24 * 60 * 60       # 24h — instrumente T212, rate-limitat 1 req/50s
DIVIDENDS_REFRESH_INTERVAL = 6 * 60 * 60   # dividendele se schimbă rar
RATINGS_REFRESH_INTERVAL = 12 * 60 * 60    # recomandările analiștilor se schimbă rar
QUALITY_REFRESH_INTERVAL = 86400
MARKET_CONTEXT_REFRESH_INTERVAL = 43200
JUSTETF_REFRESH_INTERVAL = 604800
WATCHLIST_REFRESH_INTERVAL = 86400
XTB_PRICES_REFRESH_INTERVAL = 900
_FILE_LOCKS = {}
_FILE_LOCKS_GUARD = threading.Lock()

RECOMMENDATION_LABELS = {
    "strong_buy": "Strong Buy", "buy": "Buy", "hold": "Hold",
    "sell": "Sell", "strong_sell": "Strong Sell", "none": "n/a",
}

# Mapare sector Yahoo -> ETF SPDR de sector, folosit ca proxy pentru media pieței pe sectorul respectiv
SECTOR_ETF_MAP = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP", "Energy": "XLE",
    "Industrials": "XLI", "Basic Materials": "XLB", "Real Estate": "XLRE",
    "Utilities": "XLU", "Communication Services": "XLC",
}

# Repere APROXIMATIVE, compilate manual (nu date live) pentru P/E, P/S, P/B, EV/EBITDA "uzuale" pe sector.
# Sursă: cunoștințe generale de piață, nu un feed live — de folosit orientativ, nu ca adevăr absolut.
SECTOR_TYPICAL_RANGES = {
    "Technology": {"pe": "20-35", "ps": "5-12", "pb": "5-15", "ev_ebitda": "15-25"},
    "Financial Services": {"pe": "8-14", "ps": "2-4", "pb": "1-1.8", "ev_ebitda": "n/a (bănci: nu se folosește uzual)"},
    "Healthcare": {"pe": "15-25", "ps": "3-6", "pb": "3-6", "ev_ebitda": "12-18"},
    "Consumer Cyclical": {"pe": "15-25", "ps": "1-3", "pb": "3-8", "ev_ebitda": "10-16"},
    "Consumer Defensive": {"pe": "18-24", "ps": "1-2.5", "pb": "4-8", "ev_ebitda": "12-16"},
    "Energy": {"pe": "8-14", "ps": "0.8-1.8", "pb": "1.5-2.5", "ev_ebitda": "4-7"},
    "Industrials": {"pe": "16-22", "ps": "1.5-3", "pb": "3-6", "ev_ebitda": "10-14"},
    "Basic Materials": {"pe": "10-16", "ps": "1-2", "pb": "1.5-3", "ev_ebitda": "6-10"},
    "Real Estate": {"pe": "20-35", "ps": "5-10", "pb": "1.5-2.5", "ev_ebitda": "15-22"},
    "Utilities": {"pe": "16-20", "ps": "2-3.5", "pb": "1.5-2.5", "ev_ebitda": "9-12"},
    "Communication Services": {"pe": "15-25", "ps": "2-5", "pb": "3-6", "ev_ebitda": "8-14"},
}


def load_config():
    return load_json_file(CONFIG_FILE, {"api_key_id": "", "api_secret": "", "interval_minutes": 15})


def save_config(key_id, secret, interval_minutes):
    try:
        save_json_file(
            CONFIG_FILE,
            {"api_key_id": key_id, "api_secret": secret, "interval_minutes": interval_minutes},
            raise_errors=True,
        )
        return True
    except Exception as e:
        st.error(f"Eroare la scriere pe disc: {e}")
        return False


def _get_file_lock(path):
    normalized_path = os.path.abspath(path)
    with _FILE_LOCKS_GUARD:
        lock = _FILE_LOCKS.get(normalized_path)
        if lock is None:
            lock = threading.RLock()
            _FILE_LOCKS[normalized_path] = lock
        return lock


def load_json_file(path, default):
    lock = _get_file_lock(path)
    with lock:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                return default
        return default


# momentul pornirii procesului: un job "in curs" scris inainte de el apartine unui proces oprit
PROCESS_STARTED = time.time()


def read_status(path, max_age=1800):
    status = load_json_file(path, {})
    if status.get("in_progress"):
        try:
            mtime = os.path.getmtime(path)
            # dupa un restart niciun fir vechi nu mai ruleaza, deci starea nu mai blocheaza jobul
            is_stale = (time.time() - mtime) > max_age or mtime < PROCESS_STARTED
        except Exception:
            is_stale = True
        if is_stale:
            status = dict(status)
            status["in_progress"] = False
            status["stale"] = True
    return status


def save_json_file(path, data, raise_errors=False):
    lock = _get_file_lock(path)
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        with lock:
            os.replace(tmp_path, path)
        return True
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        if raise_errors:
            raise
        return False


def update_json_file(path, default, updater):
    lock = _get_file_lock(path)
    with lock:
        current = default
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    current = json.load(f)
            except Exception:
                current = default
        updated = updater(current)
        directory = os.path.dirname(path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(updated, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        return updated


def load_ticker_map():
    return load_json_file(TICKER_MAP_FILE, {})


def save_ticker_map(mapping):
    save_json_file(TICKER_MAP_FILE, mapping)


def load_notes():
    return load_json_file(NOTES_FILE, {})


def save_note(ticker, text):
    def updater(notes):
        notes = dict(notes)
        notes[ticker] = text
        return notes

    update_json_file(NOTES_FILE, {}, updater)


def days_held_from_iso(iso_str):
    if not iso_str:
        return None
    try:
        fd = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(fd.tzinfo) - fd).days
    except Exception:
        return None


def load_portfolio_history():
    return load_json_file(PORTFOLIO_HISTORY_FILE, [])


def record_portfolio_point(market_value, invested, ppl):
    if invested <= 0 or market_value <= 0:
        return False

    now = datetime.now()
    point = {
        "ts": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "market_value": round(market_value, 2),
        "invested": round(invested, 2),
        "ppl": round(ppl, 2),
    }
    written = {"ok": False}

    def updater(history):
        history = list(history or [])
        if history:
            last_ts = history[-1].get("ts")
            if last_ts:
                try:
                    if (now - datetime.fromisoformat(last_ts)).total_seconds() < 14 * 60:
                        return history
                except Exception:
                    pass
        history.append(point)
        written["ok"] = True

        # retenție: ultimele 30 de zile complete, mai vechi doar ultimul punct din zi
        cutoff = (now - timedelta(days=30)).date().isoformat()
        recent = [p for p in history if (p.get("date") or "") >= cutoff]
        old = {}
        for p in history:
            if (p.get("date") or "") < cutoff:
                old[p.get("date")] = p
        return list(old.values()) + recent

    update_json_file(PORTFOLIO_HISTORY_FILE, [], updater)
    return written["ok"]


def check_loss_to_profit_alerts(positions, instruments_by_ticker):
    """Detectează poziții ținute > ALERT_MIN_DAYS_HELD zile care tocmai au trecut de pe
    pierdere pe profit (comparând semnul randamentului față de ultima verificare)."""
    state = load_json_file(ALERT_STATE_FILE, {})
    alerts = load_json_file(ALERTS_FILE, [])
    state_changed = alerts_changed = False

    for pos in positions:
        ticker = pos.get("ticker")
        avg_price, cur_price = pos.get("averagePrice"), pos.get("currentPrice")
        zile = days_held_from_iso(pos.get("initialFillDate"))
        if not ticker or not avg_price or cur_price is None or zile is None:
            continue
        randament = (cur_price / avg_price - 1) * 100
        current_sign = 1 if randament > 0 else (-1 if randament < 0 else 0)
        prev_sign = state.get(ticker, {}).get("last_sign")

        if prev_sign is not None and prev_sign < 0 and current_sign > 0 and zile > ALERT_MIN_DAYS_HELD:
            already_active = any(a["ticker"] == ticker and not a.get("dismissed") for a in alerts)
            if not already_active:
                name = instruments_by_ticker.get(ticker, ticker)
                alerts.append({
                    "ticker": ticker, "name": name, "triggered_at": time.time(),
                    "randament_%": randament, "zile_detinut": zile, "dismissed": False,
                })
                alerts_changed = True

        if state.get(ticker, {}).get("last_sign") != current_sign:
            state[ticker] = {"last_sign": current_sign, "last_checked": time.time()}
            state_changed = True

    if state_changed:
        save_json_file(ALERT_STATE_FILE, state)
    if alerts_changed:
        save_json_file(ALERTS_FILE, alerts)
    return alerts


def dismiss_alert(ticker, triggered_at):
    def updater(alerts):
        updated_alerts = list(alerts)
        for a in updated_alerts:
            if a["ticker"] == ticker and a["triggered_at"] == triggered_at:
                a["dismissed"] = True
        return updated_alerts

    update_json_file(ALERTS_FILE, [], updater)

# ---------------------------------------------------------------------------
# Apeluri API Trading212
# ---------------------------------------------------------------------------
BASE_URL = "https://live.trading212.com/api/v0"


# ---------------------------------------------------------------------------
# Pagina de detaliu per poziție
# ---------------------------------------------------------------------------
CHART_PERIODS = {
    "1Z": ("1d", "15m"), "1S": ("5d", "60m"), "1L": ("1mo", "1d"),
    "3L": ("3mo", "1d"), "YTD": ("ytd", "1d"), "1A": ("1y", "1d"), "5A": ("5y", "1wk"), "Max": ("max", "1mo"),
}
