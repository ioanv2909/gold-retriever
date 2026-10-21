import alerts
import health
import events
import exposure
import position_alerts
from etf import compute_etf_score, extract_etf_metrics, get_instrument
from risk import extract_risk_metrics, compute_risk
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

from core import (
    DIVIDENDS_CACHE_FILE,
    DIVIDENDS_REFRESH_INTERVAL,
    DIVIDENDS_STATUS_FILE,
    JUSTETF_REFRESH_INTERVAL,
    MARKET_CONTEXT_CACHE_FILE,
    MARKET_CONTEXT_REFRESH_INTERVAL,
    QUALITY_CACHE_FILE,
    WATCHLIST_REFRESH_INTERVAL,
    QUALITY_REFRESH_INTERVAL,
    RATINGS_CACHE_FILE,
    RATINGS_REFRESH_INTERVAL,
    RATINGS_STATUS_FILE,
    XTB_PRICES_REFRESH_INTERVAL,
    load_config,
    load_json_file,
    load_ticker_map,
    read_status,
    save_json_file,
)
from scoring import compute_score, extract_metrics
from dividend_score import compute_dividend_score, extract_dividend_metrics
from t212_api import fetch_and_cache_core, fetch_dividends_for_ticker, load_cached_snapshot
from core import record_portfolio_point
from justetf_data import start_justetf_refresh_background
from watchlist import start_watchlist_refresh_background
from xtb import first_purchase_times, load_xtb
from xtb_prices import start_xtb_prices_refresh_background
from yahoo import guess_yahoo_symbol, fetch_benchmark_return, fetch_yahoo_peg_ratio
try:
    from yahoo import resolve_yahoo_symbol
except ImportError:
    def resolve_yahoo_symbol(ticker):
        mapping = load_ticker_map()
        return mapping.get(ticker) or guess_yahoo_symbol(ticker)



# ---------------------------------------------------------------------------
# Fetch de fundal: dividende (lent, rate limit T212 6 req/min)
# ---------------------------------------------------------------------------
def load_dividends_status():
    return read_status(DIVIDENDS_STATUS_FILE)


def save_dividends_status(status):
    save_json_file(DIVIDENDS_STATUS_FILE, status)


def fetch_and_cache_dividends(key_id, secret, tickers):
    save_dividends_status({"in_progress": True, "started_at": time.time(), "total": len(tickers), "done": 0})
    dividends = {}
    err_div = None
    for idx, ticker in enumerate(tickers):
        items, err = fetch_dividends_for_ticker(key_id, secret, ticker)
        if err:
            err_div = err
            continue
        total = sum(it.get("amount", 0.0) for it in items)
        last_paid = max((it.get("paidOn") for it in items), default=None)
        dividends[ticker] = {"total": total, "count": len(items), "last_paid_on": last_paid}
        save_dividends_status({"in_progress": True, "started_at": None, "total": len(tickers), "done": idx + 1})
        if idx < len(tickers) - 1:
            time.sleep(12)

    snapshot = {"fetched_at": time.time(), "dividends": dividends, "error": err_div}
    save_json_file(DIVIDENDS_CACHE_FILE, snapshot)
    save_dividends_status({"in_progress": False, "started_at": None, "total": len(tickers), "done": len(tickers)})
    return snapshot


def start_dividends_fetch_background(key_id, secret, tickers):
    status = load_dividends_status()
    if status.get("in_progress"):
        return False
    t = threading.Thread(target=fetch_and_cache_dividends, args=(key_id, secret, tickers), daemon=True)
    t.start()
    return True


# ---------------------------------------------------------------------------
# Fetch de fundal: recomandări analiști per poziție (pentru filtrul din tabel)
# ---------------------------------------------------------------------------
def load_ratings_status():
    return read_status(RATINGS_STATUS_FILE)


def save_ratings_status(status):
    save_json_file(RATINGS_STATUS_FILE, status)


def fetch_rating_for_symbol(yahoo_symbol):
    rec, target, err = fetch_rating_and_target(yahoo_symbol)
    return rec, err


def fetch_rating_and_target(yahoo_symbol):
    """(recomandare, {upside, n}, eroare). Tinta si pretul vin din acelasi info, deci in aceeasi unitate (si la GBp)."""
    if not YFINANCE_AVAILABLE:
        return None, None, "yfinance indisponibil"
    try:
        info = yf.Ticker(yahoo_symbol).info or {}
        mean, price = info.get("targetMeanPrice"), info.get("currentPrice") or info.get("regularMarketPrice")
        target = {"upside": (mean / price - 1) * 100, "n": info.get("numberOfAnalystOpinions")} if mean and price else None
        return info.get("recommendationKey", "none"), target, None
    except Exception as e:
        return None, None, str(e)


def fetch_and_cache_ratings(tickers_t212):
    save_ratings_status({"in_progress": True, "started_at": time.time(), "total": len(tickers_t212), "done": 0})
    mapping = load_ticker_map()
    ratings, targets = {}, {}
    for idx, t212_ticker in enumerate(tickers_t212):
        ysym = mapping.get(t212_ticker) or guess_yahoo_symbol(t212_ticker)
        rec, target, err = fetch_rating_and_target(ysym)
        ratings[t212_ticker] = rec or "none"
        if target:
            targets[t212_ticker] = target
        save_ratings_status({"in_progress": True, "started_at": None, "total": len(tickers_t212), "done": idx + 1})
        if idx < len(tickers_t212) - 1:
            time.sleep(1.5)  # yfinance nu are rate limit oficial, dar o pauză mică e mai politicos

    snapshot = {"fetched_at": time.time(), "ratings": ratings, "targets": targets}
    save_json_file(RATINGS_CACHE_FILE, snapshot)
    save_ratings_status({"in_progress": False, "started_at": None, "total": len(tickers_t212), "done": len(tickers_t212)})
    return snapshot


def start_ratings_fetch_background(tickers):
    status = load_ratings_status()
    if status.get("in_progress"):
        return False
    t = threading.Thread(target=fetch_and_cache_ratings, args=(tickers,), daemon=True)
    t.start()
    return True


# ---------------------------------------------------------------------------
# Fetch de fundal: scor de calitate per poziție
# ---------------------------------------------------------------------------
from userctx import UPath
QUALITY_STATUS_FILE = UPath("quality_status.json", shared=True)
MARKET_CONTEXT_STATUS_FILE = UPath("market_context_status.json", shared=True)
MANUAL_METRICS_FILE = UPath("manual_metrics.json", shared=True)


def load_quality_status():
    return read_status(QUALITY_STATUS_FILE)


def save_quality_status(status):
    save_json_file(QUALITY_STATUS_FILE, status)


def load_quality_cache():
    return load_json_file(QUALITY_CACHE_FILE, {})


def load_market_context_cache():
    return load_json_file(MARKET_CONTEXT_CACHE_FILE, {})


def fetch_and_cache_market_context(positions):
    save_json_file(MARKET_CONTEXT_STATUS_FILE, {"in_progress": True, "started_at": time.time(), "total": len(positions), "done": 0})
    cache = load_market_context_cache()
    now = datetime.now()

    for idx, p in enumerate(positions):
        try:
            ticker = p.get("ticker")
            if not ticker:
                continue

            fill_iso = None
            raw_fill = p.get("initialFillDate")
            if raw_fill:
                try:
                    fill_iso = datetime.fromisoformat(raw_fill.replace("Z", "+00:00")).strftime("%Y-%m-%d")
                except Exception:
                    fill_iso = None

            cached_entry = cache.get(ticker)
            if cached_entry and cached_entry.get("updated") and cached_entry.get("fill_iso") == fill_iso:
                try:
                    updated_dt = datetime.fromisoformat(cached_entry["updated"])
                    if (now - updated_dt).total_seconds() < MARKET_CONTEXT_REFRESH_INTERVAL:
                        save_json_file(MARKET_CONTEXT_STATUS_FILE, {"in_progress": True, "started_at": None, "total": len(positions), "done": idx + 1})
                        continue
                except Exception:
                    pass

            yahoo_symbol = resolve_yahoo_symbol(ticker)
            peg = fetch_yahoo_peg_ratio(yahoo_symbol) if yahoo_symbol else None
            bench_total = None
            if fill_iso:
                bench_total, bench_err = fetch_benchmark_return("^SP500TR", fill_iso)
                if bench_err:
                    bench_total = None

            cache[ticker] = {
                "sp500_return_%": bench_total,
                "peg": peg,
                "fill_iso": fill_iso,
                "updated": datetime.now().isoformat(),
            }
            save_json_file(MARKET_CONTEXT_CACHE_FILE, cache)
        except Exception as e:
            print(f"[market] {ticker}: {e}", flush=True)
        finally:
            save_json_file(MARKET_CONTEXT_STATUS_FILE, {"in_progress": True, "started_at": None, "total": len(positions), "done": idx + 1})
            if idx < len(positions) - 1:
                time.sleep(0.5)

    save_json_file(MARKET_CONTEXT_STATUS_FILE, {"in_progress": False, "started_at": None, "total": len(positions), "done": len(positions)})
    return cache


def start_market_context_fetch_background(positions):
    status = read_status(MARKET_CONTEXT_STATUS_FILE)
    if status.get("in_progress"):
        return False
    t = threading.Thread(target=fetch_and_cache_market_context, args=(positions,), daemon=True)
    t.start()
    return True


def fetch_and_cache_quality(tickers_t212):
    save_quality_status({"in_progress": True, "started_at": time.time(), "total": len(tickers_t212), "done": 0})
    cache = load_quality_cache()
    manual_metrics_all = load_json_file(MANUAL_METRICS_FILE, {})
    now = datetime.now()

    xtb_info = {i["ticker"]: i for i in xtb_instruments()}

    for idx, ticker in enumerate(tickers_t212):
        try:
            cached_entry = cache.get(ticker)
            if cached_entry and cached_entry.get("updated"):
                try:
                    updated_dt = datetime.fromisoformat(cached_entry["updated"])
                    if (now - updated_dt).total_seconds() < QUALITY_REFRESH_INTERVAL and "risk_total" in cached_entry and "div_pays" in cached_entry and cached_entry.get("rating") != "ISIN lipsă":
                        save_quality_status({"in_progress": True, "started_at": None, "total": len(tickers_t212), "done": idx + 1})
                        continue
                except Exception:
                    pass

            if not YFINANCE_AVAILABLE:
                save_quality_status({"in_progress": True, "started_at": None, "total": len(tickers_t212), "done": idx + 1})
                continue

            yahoo_symbol = resolve_yahoo_symbol(ticker)
            tk = yf.Ticker(yahoo_symbol)
            instr = get_instrument(ticker)
            xi = xtb_info.get(ticker)
            kind = "stock"
            is_etf = False
            etf_isin = None
            if instr and instr.get("type") == "ETF":
                is_etf, etf_isin = True, instr.get("isin")
            elif xi and xi.get("category") in ("ETF", "ETC"):
                is_etf, etf_isin = True, xi.get("isin")

            if is_etf:
                metrics = {}
                if etf_isin:
                    em, _, _ = extract_etf_metrics(etf_isin, yahoo_symbol, manual=None)
                    score_res = compute_etf_score(em)
                else:
                    score_res = {"total": None, "rating": "ISIN lipsă", "coverage": 0.0}
                kind = "etf"
            else:
                metrics, _ = extract_metrics(tk)

                manual_overrides = manual_metrics_all.get(ticker) or manual_metrics_all.get(yahoo_symbol)
                if isinstance(manual_overrides, dict):
                    for k, v in manual_overrides.items():
                        if v is not None:
                            metrics[k] = v

                score_res = compute_score(metrics)
            try:
                risk_m, _ = extract_risk_metrics(tk, metrics)
                risk_res = compute_risk(risk_m)
            except Exception as e:
                print(f"[risk] {ticker}: {e}", flush=True)
                risk_res = {}
            div_res, div_pays = {}, False
            if not is_etf:
                try:
                    div_m, div_pays = extract_dividend_metrics(tk)
                    if div_pays:
                        div_res = compute_dividend_score(div_m)
                except Exception as e:
                    print(f"[dividend] {ticker}: {e}", flush=True)
            cache[ticker] = {
                "kind": kind,
                "total": score_res.get("total"),
                "rating": score_res.get("rating"),
                "coverage": score_res.get("coverage"),
                "risk_total": risk_res.get("total"),
                "risk_rating": risk_res.get("rating"),
                "risk_coverage": risk_res.get("coverage"),
                "div_pays": div_pays,
                "div_total": div_res.get("total"),
                "div_rating": div_res.get("rating"),
                "div_coverage": div_res.get("coverage"),
                "updated": datetime.now().isoformat(),
            }
            save_json_file(QUALITY_CACHE_FILE, cache)
        except Exception as e:
            print(f"[quality] {ticker}: {e}", flush=True)
        finally:
            save_quality_status({"in_progress": True, "started_at": None, "total": len(tickers_t212), "done": idx + 1})
            if idx < len(tickers_t212) - 1:
                time.sleep(1)

    save_quality_status({"in_progress": False, "started_at": None, "total": len(tickers_t212), "done": len(tickers_t212)})
    return cache


def start_quality_fetch_background(tickers):
    status = load_quality_status()
    if status.get("in_progress"):
        return False
    t = threading.Thread(target=fetch_and_cache_quality, args=(tickers,), daemon=True)
    t.start()
    return True


# ---------------------------------------------------------------------------
# Scheduler de fundal — un singur thread per proces, cu trei cicluri
# independente (core rapid / dividende / recomandări), fiecare citind
# config.json proaspăt la fiecare tur, ca schimbările din UI să se aplice
# imediat fără scheduler-e orfane.
# ---------------------------------------------------------------------------
from xtb import instruments as xtb_instruments
from history_multi import record_multi_point


def ticker_isins(tickers):
    """{ticker: ISIN} din instrumentele Trading 212 si XTB (pentru tarile ETF din justETF)."""
    xtb_isins = {i["ticker"]: i.get("isin") for i in xtb_instruments() if i.get("ticker")}
    out = {}
    for t in tickers:
        try:
            isin = (get_instrument(t) or {}).get("isin") or xtb_isins.get(t)
        except Exception:
            isin = xtb_isins.get(t)
        if isin:
            out[t] = isin
    return out


def xtb_tickers():
    return [i["ticker"] for i in xtb_instruments() if i.get("ticker")]


def _iso_with_timezone(value):
    if not value:
        return None

    text = str(value)
    if text.endswith("Z"):
        return f"{text[:-1]}+00:00"
    if (
        len(text) >= 6
        and text[-6] in "+-"
        and text[-5:-3].isdigit()
        and text[-3] == ":"
        and text[-2:].isdigit()
    ):
        return text
    if len(text) >= 5 and text[-5] in "+-" and text[-4:].isdigit():
        return text
    return f"{text}+00:00"


def xtb_positions_for_context():
    out = {}
    for account_key, acc in (load_xtb().get("accounts") or {}).items():
        first_purchase_by_ticker = first_purchase_times(account_key)

        for g in acc.get("positions") or []:
            t = g.get("ticker")
            if not t:
                continue
            fill = _iso_with_timezone(g.get("initial_fill") or first_purchase_by_ticker.get(t))
            cur = out.get(t)
            if cur is None or (fill and (not cur["initialFillDate"] or str(fill) < str(cur["initialFillDate"]))):
                out[t] = {"ticker": t, "initialFillDate": fill}
    return list(out.values())


@st.cache_resource
def start_background_scheduler(user=None):
    def run_loop():
        last_core = last_div = last_rat = last_q = last_m = last_w = last_j = last_x = last_h = 0.0
        last_hc = last_ev = last_evn = last_pa = last_ex = 0.0
        while True:
            cfg = load_config()
            key_id, secret = cfg.get("api_key_id"), cfg.get("api_secret")
            interval_s = max(1, int(cfg.get("interval_minutes", 15))) * 60

            if key_id and secret and (time.time() - last_core) >= interval_s:
                snap_c = fetch_and_cache_core(key_id, secret)
                last_core = time.time()
                try:
                    errs_c = dict((snap_c or {}).get("errors") or {})
                    errs_c.update({"stale-" + k: v for k, v in ((snap_c or {}).get("stale_errors") or {}).items()})
                    alerts.record_refresh("Trading 212", user or "default", errs_c, secrets=(key_id, secret))
                    bad_c = [v for v in (snap_c or {}).get("errors", {}).values() if v]
                    health.record("t212", not bad_c, error=alerts._mask(bad_c[0], (key_id, secret)) if bad_c else None)
                except Exception as e:
                    print(f"[alerts] {e}", flush=True)
                try:
                    snap_h = load_cached_snapshot()
                    cash_h = (snap_h or {}).get("cash") or {}
                    inv_h = cash_h.get("invested", 0.0)
                    ppl_h = cash_h.get("ppl", 0.0)
                    record_portfolio_point(inv_h + ppl_h, inv_h, ppl_h)
                except Exception:
                    pass

            snap = load_cached_snapshot()
            tickers = [p.get("ticker") for p in (snap.get("positions") or [])] if snap else []
            all_tickers = list(tickers) + [t for t in xtb_tickers() if t not in tickers]

            if key_id and secret and tickers and (time.time() - last_div) >= DIVIDENDS_REFRESH_INTERVAL:
                if not load_dividends_status().get("in_progress") and start_dividends_fetch_background(key_id, secret, tickers):
                    last_div = time.time()

            if all_tickers and (time.time() - last_rat) >= RATINGS_REFRESH_INTERVAL:
                if not load_ratings_status().get("in_progress") and start_ratings_fetch_background(all_tickers):
                    last_rat = time.time()

            if (time.time() - last_j) >= JUSTETF_REFRESH_INTERVAL:
                start_justetf_refresh_background()
                last_j = time.time()

            if all_tickers and (time.time() - last_q) >= QUALITY_REFRESH_INTERVAL:
                if start_quality_fetch_background(all_tickers):
                    last_q = time.time()

            if all_tickers and (time.time() - last_m) >= MARKET_CONTEXT_REFRESH_INTERVAL:
                if start_market_context_fetch_background(((snap or {}).get("positions") or []) + xtb_positions_for_context()):
                    last_m = time.time()

            if (load_xtb().get("accounts") or {}) and (time.time() - last_x) >= XTB_PRICES_REFRESH_INTERVAL:
                started = start_xtb_prices_refresh_background()
                if started:
                    last_x = time.time()

            if (time.time() - last_w) >= WATCHLIST_REFRESH_INTERVAL:
                if start_watchlist_refresh_background():
                    last_w = time.time()

            if all_tickers and (time.time() - last_ev) >= 3600:
                # tickerele deja proaspete sunt sarite, deci un tur pe ora e ieftin
                if events.start_events_fetch_background(all_tickers):
                    last_ev = time.time()

            if all_tickers and (time.time() - last_ex) >= 3600:
                # doar tickerele noi sau mai vechi de o saptamana se cer din nou
                if exposure.start_fetch_background(all_tickers, ticker_isins(all_tickers)):
                    last_ex = time.time()

            if all_tickers and (time.time() - last_evn) >= 3600:
                last_evn = time.time()
                try:
                    events.notify_upcoming(all_tickers, user)
                except Exception as e:
                    print(f"[events] {e}", flush=True)

            if (time.time() - last_pa) >= position_alerts.EVAL_INTERVAL:
                last_pa = time.time()
                try:
                    position_alerts.evaluate(user)
                except Exception as e:
                    print(f"[position_alerts] {e}", flush=True)

            if (time.time() - last_h) >= 300:
                try:
                    record_multi_point()
                except Exception as e:
                    print(f"[history] {e}", flush=True)
                last_h = time.time()

            if (time.time() - last_hc) >= 600:
                last_hc = time.time()
                try:
                    from t212_api import load_cached_dividends as _lcd
                    alerts.check_backup()
                    alerts.record_refresh("dividende", user or "default", {"dividends": (_lcd() or {}).get("error")})
                except Exception as e:
                    print(f"[alerts] {e}", flush=True)

            time.sleep(5)

    def _as_user():
        if user:
            from userctx import set_user
            set_user(user)
        run_loop()

    t = threading.Thread(target=_as_user, daemon=True)
    t.start()
    return t
