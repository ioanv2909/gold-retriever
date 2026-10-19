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
    """Moneda de bază a contului T212 (rate limit: 1 req/30s) — cache lung, se schimbă practic niciodată."""
    if os.path.exists(ACCOUNT_INFO_CACHE_FILE):
        try:
            with open(ACCOUNT_INFO_CACHE_FILE, "r") as f:
                cached = json.load(f)
            if time.time() - cached.get("fetched_at", 0) < INSTRUMENTS_CACHE_TTL:
                return cached["currencyCode"], None
        except Exception:
            pass
    if not key_id or not secret:
        return None, "Lipsește ID-ul sau Cheia Secretă."
    try:
        r = requests.get(f"{BASE_URL}/equity/account/info", headers=_headers(key_id, secret), timeout=15)
        if r.status_code == 200:
            code = r.json().get("currencyCode")
            save_json_file(ACCOUNT_INFO_CACHE_FILE, {"fetched_at": time.time(), "currencyCode": code})
            return code, None
        return None, f"Eroare API account/info ({r.status_code}): {r.text}"
    except Exception as e:
        return None, f"Eroare rețea: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
@st.cache_data(ttl=600, show_spinner=False)
def fetch_fx_rate(from_ccy, to_ccy):
    """Curs valutar curent from_ccy -> to_ccy, via Yahoo Finance. 1.0 dacă monedele coincid sau la eșec.
    GBX (penny sterling, folosit de LSE) nu e o monedă valutară reală — se rezolvă via GBP/100."""
    if from_ccy == "GBX":
        rate, err = fetch_fx_rate("GBP", to_ccy)
        return rate / 100, err
    if not from_ccy or not to_ccy or from_ccy == to_ccy or not YFINANCE_AVAILABLE:
        return 1.0, None
    try:
        hist = yf.Ticker(f"{from_ccy}{to_ccy}=X").history(period="5d")
        if hist.empty:
            return 1.0, f"Nu am găsit curs {from_ccy}->{to_ccy} pe Yahoo Finance."
        return float(hist["Close"].iloc[-1]), None
    except Exception as e:
        return 1.0, f"Eroare curs {from_ccy}->{to_ccy}: {e}"


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
