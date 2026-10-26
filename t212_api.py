from yf_compat import yf, YFINANCE_AVAILABLE
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

from core import ACCOUNT_INFO_CACHE_FILE, BASE_URL, DIVIDENDS_CACHE_FILE, INSTRUMENTS_CACHE_FILE, INSTRUMENTS_CACHE_TTL, PORTFOLIO_CACHE_FILE, RATINGS_CACHE_FILE, load_json_file, save_json_file



def _headers(key_id, secret):
    creds = f"{key_id}:{secret}"
    encoded = base64.b64encode(creds.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


def fetch_cash(key_id, secret):
    if not key_id or not secret:
        return None, "Lipsește ID-ul sau Cheia Secretă."
    try:
        r = requests.get(f"{BASE_URL}/equity/account/cash", headers=_headers(key_id, secret), timeout=15)
        if r.status_code == 200:
            return r.json(), None
        return None, f"Eroare API cash ({r.status_code}): {r.text}"
    except Exception as e:
        return None, f"Eroare rețea: {e}"


def fetch_portfolio(key_id, secret):
    if not key_id or not secret:
        return None, "Lipsește ID-ul sau Cheia Secretă."
    try:
        r = requests.get(f"{BASE_URL}/equity/portfolio", headers=_headers(key_id, secret), timeout=15)
        if r.status_code == 200:
            data = r.json()
            return (data if data else []), None
        return None, f"Eroare API portfolio ({r.status_code}): {r.text}"
    except Exception as e:
        return None, f"Eroare rețea: {e}"


def fetch_instruments(key_id, secret):
    if os.path.exists(INSTRUMENTS_CACHE_FILE):
        try:
            with open(INSTRUMENTS_CACHE_FILE, "r") as f:
                cached = json.load(f)
            if time.time() - cached.get("fetched_at", 0) < INSTRUMENTS_CACHE_TTL:
                return cached["data"], None
        except Exception:
            pass

    if not key_id or not secret:
        return None, "Lipsește ID-ul sau Cheia Secretă."
    try:
        r = requests.get(f"{BASE_URL}/equity/metadata/instruments", headers=_headers(key_id, secret), timeout=30)
        if r.status_code == 200:
            data = r.json()
            save_json_file(INSTRUMENTS_CACHE_FILE, {"fetched_at": time.time(), "data": data})
            return data, None
        return None, f"Eroare API instruments ({r.status_code}): {r.text}"
    except Exception as e:
        return None, f"Eroare rețea: {e}"


def fetch_account_currency(key_id, secret):
    """Moneda de bază a contului T212 (rate limit: 1 req/30s) — cache lung, se schimbă practic niciodată.
    Dacă cererea eșuează (limită, rețea), se folosește moneda din cache chiar expirat."""
    stale = None
    if os.path.exists(ACCOUNT_INFO_CACHE_FILE):
        try:
            with open(ACCOUNT_INFO_CACHE_FILE, "r") as f:
                cached = json.load(f)
            stale = cached.get("currencyCode") or None
            if stale and time.time() - cached.get("fetched_at", 0) < INSTRUMENTS_CACHE_TTL:
                return stale, None
        except Exception:
            pass
    if not key_id or not secret:
        return stale, None if stale else "Lipsește ID-ul sau Cheia Secretă."
    try:
        r = requests.get(f"{BASE_URL}/equity/account/info", headers=_headers(key_id, secret), timeout=15)
        if r.status_code == 200 and r.json().get("currencyCode"):
            code = r.json().get("currencyCode")
            save_json_file(ACCOUNT_INFO_CACHE_FILE, {"fetched_at": time.time(), "currencyCode": code})
            return code, None
        err = f"Eroare API account/info ({r.status_code}): {r.text}"
    except Exception as e:
        err = f"Eroare rețea: {e}"
    return (stale, None) if stale else (None, err)


FX_LAST_GOOD_FILE = os.path.join("data", "fx_last_good.json")
FX_LAST_GOOD_MAX_AGE = 7 * 86400   # un curs bun mai vechi nu mai inlocuieste unul care lipseste
_FX_SAVE_EVERY = 3600               # scrieri pe disc pentru aceeasi pereche
_fx_last_good = {}                  # "EURRON" -> (ts, curs)
_fx_saved = {}
_fx_state = {"loaded": False, "failures": 0}


def _fx_good(pair, now):
    if not _fx_state["loaded"]:
        _fx_state["loaded"] = True
        d = load_json_file(FX_LAST_GOOD_FILE, {})
        for k, v in (d.items() if isinstance(d, dict) else []):
            if isinstance(v, list) and len(v) == 2 and k not in _fx_last_good:
                _fx_last_good[k] = (float(v[0]), float(v[1]))
    ts_rate = _fx_last_good.get(pair)
    return ts_rate[1] if ts_rate and now - ts_rate[0] <= FX_LAST_GOOD_MAX_AGE else None


def _fx_remember(pair, rate, now):
    _fx_good(pair, now)  # incarca fisierul inainte de prima scriere
    _fx_last_good[pair] = (now, rate)
    if now - _fx_saved.get(pair, 0) >= _FX_SAVE_EVERY:
        _fx_saved[pair] = now
        save_json_file(FX_LAST_GOOD_FILE, {k: [t, r] for k, (t, r) in _fx_last_good.items()})


def fx_failures():
    """Numarul de cursuri care au cazut pe 1.0 (fara curs cunoscut) de la pornire."""
    return _fx_state["failures"]


@st.cache_data(ttl=600, show_spinner=False)
def _yahoo_fx(pair):
    """Cursul de pe Yahoo; arunca exceptie la esec, deci un esec nu ramane in cache."""
    hist = yf.Ticker(f"{pair}=X").history(period="5d")
    if hist.empty:
        raise ValueError(f"Nu am găsit curs {pair} pe Yahoo Finance.")
    rate = float(hist["Close"].iloc[-1])
    if not rate > 0:
        raise ValueError(f"Curs invalid {pair}: {rate}")
    return rate


def fetch_fx_rate(from_ccy, to_ccy):
    """Curs valutar curent from_ccy -> to_ccy, via Yahoo Finance. 1.0 dacă monedele coincid.
    La eșec se folosește ultimul curs bun (cel mult 7 zile, păstrat și pe disc); fără el, 1.0 cu eroare
    și fx_failures() crește, ca istoricul să nu salveze puncte calculate cu un curs inventat.
    GBX (penny sterling, folosit de LSE) nu e o monedă valutară reală — se rezolvă via GBP/100."""
    if from_ccy == "GBX":
        rate, err = fetch_fx_rate("GBP", to_ccy)
        return rate / 100, err
    if not from_ccy or not to_ccy or from_ccy == to_ccy or not YFINANCE_AVAILABLE:
        return 1.0, None
    pair = f"{from_ccy}{to_ccy}"
    now = time.time()
    try:
        rate = _yahoo_fx(pair)
        _fx_remember(pair, rate, now)
        return rate, None
    except Exception as e:
        err = f"Eroare curs {from_ccy}->{to_ccy}: {e}"
    good = _fx_good(pair, now)
    if good is not None:
        return good, None
    _fx_state["failures"] += 1
    return 1.0, err


def fetch_order_history_for_ticker(key_id, secret, ticker, limit=50):
    """Istoricul tranzacțiilor executate pentru un ticker. Rate limit T212: 6 req/minut."""
    if not key_id or not secret:
        return None, "Lipsește ID-ul sau Cheia Secretă."
    try:
        r = requests.get(
            f"{BASE_URL}/equity/history/orders",
            headers=_headers(key_id, secret),
            params={"ticker": ticker, "limit": limit},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("items", []), None
        return None, f"Eroare API orders ({r.status_code}): {r.text}"
    except Exception as e:
        return None, f"Eroare rețea: {e}"


def fetch_dividends_for_ticker(key_id, secret, ticker):
    for attempt in range(2):
        try:
            r = requests.get(
                f"{BASE_URL}/equity/history/dividends",
                headers=_headers(key_id, secret),
                params={"ticker": ticker, "limit": 50},
                timeout=15,
            )
            if r.status_code == 200:
                return r.json().get("items", []), None
            if r.status_code == 429 and attempt == 0:
                time.sleep(20)  # rate limit T212 — mai așteptăm și reîncercăm o dată
                continue
            return None, f"Eroare API dividends ({r.status_code}): {r.text}"
        except Exception as e:
            return None, f"Eroare rețea: {e}"
    return None, "Eroare API dividends (429): prea multe cereri, reîncearcă mai târziu."


def fetch_and_cache_core(key_id, secret):
    """Cash + poziții + instrumente — rapid, apelat des (buton manual + scheduler).
    Dacă un apel eșuează și există un snapshot anterior bun, păstrează datele vechi."""
    cash, err_cash = fetch_cash(key_id, secret)
    positions, err_pf = fetch_portfolio(key_id, secret)
    instruments, err_instr = fetch_instruments(key_id, secret)

    prev = load_cached_snapshot() or {}
    stale = {}
    if err_cash and prev.get("cash"):
        stale["cash"] = err_cash
        cash, err_cash = prev["cash"], None
    if err_pf and prev.get("positions"):
        stale["portfolio"] = err_pf
        positions, err_pf = prev["positions"], None
    if err_instr and prev.get("instruments"):
        stale["instruments"] = err_instr
        instruments, err_instr = prev["instruments"], None

    snapshot = {
        "fetched_at": prev.get("fetched_at", time.time()) if stale else time.time(),
        "cash": cash,
        "positions": positions,
        "instruments": instruments,
        "errors": {"cash": err_cash, "portfolio": err_pf, "instruments": err_instr},
        "stale_errors": stale,
    }
    try:
        save_json_file(PORTFOLIO_CACHE_FILE, snapshot, raise_errors=True)
    except Exception as e:
        print(f"Nu am putut scrie cache-ul de portofoliu: {e}")
    return snapshot


def load_cached_snapshot():
    return load_json_file(PORTFOLIO_CACHE_FILE, None)


def load_cached_dividends():
    return load_json_file(DIVIDENDS_CACHE_FILE, None)


def load_cached_ratings():
    return load_json_file(RATINGS_CACHE_FILE, None)
