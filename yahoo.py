from yf_compat import yf, YFINANCE_AVAILABLE
from price_clean import clean_history, is_fund
import streamlit as st
import requests
import pandas as pd
import numpy as np
import base64
import os
import json
import re
import time
import threading
import tempfile
from datetime import datetime
from urllib.parse import quote
import plotly.graph_objects as go
import plotly.express as px

from core import SECTOR_ETF_MAP, load_ticker_map


XTB_YAHOO_SUFFIX = {
    "US": "",
    "DE": ".DE",
    "UK": ".L",
    "FR": ".PA",
    "NL": ".AS",
    "ES": ".MC",
    "IT": ".MI",
    "PL": ".WA",
    "CH": ".SW",
    "PT": ".LS",
    "BE": ".BR",
    "DK": ".CO",
    "SE": ".ST",
    "NO": ".OL",
    "FI": ".HE",
    "AT": ".VI",
    "IE": ".IR",
    "CZ": ".PR",
    "HU": ".BD",
}


# ---------------------------------------------------------------------------
# Mapare Ticker T212 -> Simbol Yahoo Finance
# ---------------------------------------------------------------------------
def guess_yahoo_symbol(ticker):
    if ticker.endswith("_US_EQ"):
        return ticker[:-6]
    if ticker.endswith("_EQ"):
        base = ticker[:-3]
        if base and base[-1].islower():
            exch_letter = base[-1]
            symbol = base[:-1]
            suffix_map = {"l": ".L", "d": ".DE", "p": ".PA", "m": ".MI", "a": ".AS", "s": ".SW"}
            return symbol + suffix_map.get(exch_letter, "")
        return base
    if re.match(r"^[A-Z0-9]+\.[A-Z]{2}$", ticker):
        base, suffix = ticker.rsplit(".", 1)
        if suffix in XTB_YAHOO_SUFFIX:
            return base + XTB_YAHOO_SUFFIX[suffix]
    return ticker


def resolve_yahoo_symbol(ticker):
    mapping = load_ticker_map()
    if ticker in mapping:
        return mapping[ticker]
    from symbol_resolver import lookup
    return lookup(ticker) or guess_yahoo_symbol(ticker)


# ---------------------------------------------------------------------------
# Calcule tehnice
# ---------------------------------------------------------------------------
def calc_rsi(closes, period=14):
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None


def calc_atr(hist, period=14):
    try:
        high, low, close = hist["High"], hist["Low"], hist["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr.iloc[-1] if not atr.empty else None
    except Exception:
        return None


def pct_change_over(closes, trading_days):
    if len(closes) < trading_days + 1:
        return None
    return (closes.iloc[-1] / closes.iloc[-(trading_days + 1)] - 1) * 100


def pct_change_ytd(closes):
    try:
        this_year = closes.index[-1].year
        year_closes = closes[closes.index.year == this_year]
        if year_closes.empty:
            return None
        return (closes.iloc[-1] / year_closes.iloc[0] - 1) * 100
    except Exception:
        return None


def annualize(total_return_pct, days_held):
    return ((1 + total_return_pct / 100) ** (365 / days_held) - 1) * 100


def sales_growth_3y_cagr(tk):
    try:
        fin = tk.financials
        if fin is None or fin.empty:
            return None
        row = None
        for candidate in ["Total Revenue", "TotalRevenue"]:
            if candidate in fin.index:
                row = fin.loc[candidate].dropna().sort_index()
                break
        if row is None or len(row) < 2:
            return None
        n_years = len(row) - 1
        oldest, newest = row.iloc[0], row.iloc[-1]
        if oldest <= 0 or n_years <= 0:
            return None
        return ((newest / oldest) ** (1 / n_years) - 1) * 100
    except Exception:
        return None


def eps_5y_growth_estimate(tk):
    try:
        ge = tk.growth_estimates
        if ge is None or ge.empty:
            return None
        for label in ["+5Y", "+5y", "5y", "5Y"]:
            if label in ge.index:
                val = ge.loc[label].get("stock")
                if val is not None and not pd.isna(val):
                    val = float(val)
                    return val * 100 if abs(val) < 3 else val  # fracție vs. deja-procent, euristică
        return None
    except Exception:
        return None


def insider_tx_summary(tk):
    """Returnează (text_scurt, text_complet) — text_scurt pentru afișare, text_complet pentru tooltip."""
    try:
        itx = tk.insider_transactions
        if itx is None or itx.empty:
            return None, None
        recent = itx.head(10)
        text_col = next((c for c in ["Transaction", "Text", "transactionText"] if c in recent.columns), None)
        if text_col is None:
            short = f"{len(recent)} tranzacții recente"
            return short, f"{short} (detaliu indisponibil în structura primită de la Yahoo Finance)"
        col = recent[text_col].astype(str)
        buys = col.str.contains("Buy|Purchase", case=False, na=False).sum()
        sells = col.str.contains("Sale|Sell", case=False, na=False).sum()
        short = f"{buys} cump. / {sells} vânz."
        full = f"{buys} cumpărări / {sells} vânzări din ultimele {len(recent)} tranzacții insideri raportate."
        return short, full
    except Exception:
        return None, None


@st.cache_data(ttl=600, show_spinner=False)
def fetch_yahoo_analysis(yahoo_symbol):
    """Date fundamentale + tehnice extinse de la Yahoo Finance."""
    if not YFINANCE_AVAILABLE:
        return None, "Pachetul yfinance nu e instalat în imagine."
    try:
        tk = yf.Ticker(yahoo_symbol)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=5) as _ex:
            _f_info = _ex.submit(lambda: tk.info or {})
            _f_hist = _ex.submit(lambda: tk.history(period="10y"))
            _f_eps = _ex.submit(eps_5y_growth_estimate, tk)
            _f_ins = _ex.submit(insider_tx_summary, tk)
            _f_sales = _ex.submit(sales_growth_3y_cagr, tk)
        info = _f_info.result()
        hist = _f_hist.result()
        if hist.empty:
            return None, f"Yahoo Finance nu are date pentru simbolul „{yahoo_symbol}”."
        _qt = info.get("quoteType")
        _fund = True if _qt in ("ETF", "MUTUALFUND") else (False if _qt else None)
        hist, _clean_notes = clean_history(hist, fund=_fund)

        # Yahoo dă instrumentele LSE în pence (GBp), nu în GBP — normalizăm ca să fie
        # consistent cu conversia GBX->GBP făcută pe partea T212 din tabelul principal.
        yahoo_ccy = info.get("currency")
        gbp_scale = 100.0 if yahoo_ccy == "GBp" else 1.0
        display_ccy = "GBP" if yahoo_ccy == "GBp" else yahoo_ccy

        closes = hist["Close"] / gbp_scale
        current_price = closes.iloc[-1]
        sma20 = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else None
        sma50 = closes.rolling(50).mean().iloc[-1] if len(closes) >= 50 else None
        sma200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else None
        rsi14 = calc_rsi(closes, 14)
        atr14 = calc_atr(hist.tail(60), 14)
        if gbp_scale != 1.0:
            atr14 = atr14 / gbp_scale if atr14 is not None else None
        daily_returns = closes.pct_change().dropna()
        volatility_annual = daily_returns.tail(252).std() * (252 ** 0.5) * 100 if not daily_returns.empty else None

        week52_high = info.get("fiftyTwoWeekHigh")
        week52_low = info.get("fiftyTwoWeekLow")
        if _clean_notes:
            _tail = hist.tail(252)
            week52_high = float(_tail["High"].max()) if "High" in _tail.columns else week52_high
            week52_low = float(_tail["Low"].min()) if "Low" in _tail.columns else week52_low
        target_mean_price = info.get("targetMeanPrice")
        if gbp_scale != 1.0:
            week52_high = week52_high / gbp_scale if week52_high is not None else None
            week52_low = week52_low / gbp_scale if week52_low is not None else None
            target_mean_price = target_mean_price / gbp_scale if target_mean_price is not None else None

        div_y = info.get("dividendYield")  # Yahoo dă asta deja ca procent (ex. 2.1 = 2.1%), nu ca fracție
        insider_tx_short, insider_tx_full = _f_ins.result()

        # descriere companie/ETF — stocurile au longBusinessSummary; ETF-urile de regulă nu, dar au
        # category/fundFamily, care oferă cel puțin un context minim
        business_summary = info.get("longBusinessSummary")
        if not business_summary:
            cat, family = info.get("category"), info.get("fundFamily")
            if cat or family:
                business_summary = f"ETF/fond {family or ''} · categorie: {cat or 'n/a'}".strip(" ·")

        def unix_to_date(ts):
            try:
                return datetime.fromtimestamp(ts).strftime("%d.%m.%Y") if ts else None
            except Exception:
                return None

        result = {
            "current_price": current_price,
            "currency": display_ccy,
            "business_summary": business_summary,
            "next_dividend_date": unix_to_date(info.get("dividendDate")),
            "ex_dividend_date": unix_to_date(info.get("exDividendDate")),
            "enterprise_value": info.get("enterpriseValue"),
            "book_value_per_share": info.get("bookValue"),
            "cash_per_share": info.get("totalCashPerShare"),
            "quick_ratio": info.get("quickRatio"),
            "current_ratio": info.get("currentRatio"),
            "debt_to_equity": info.get("debtToEquity"),
            "payout_ratio_pct": (info.get("payoutRatio") * 100) if info.get("payoutRatio") is not None else None,
            "short_pct_float_pct": (info.get("shortPercentOfFloat") * 100) if info.get("shortPercentOfFloat") is not None else None,
            "short_ratio": info.get("shortRatio"),
            "avg_volume": info.get("averageVolume"),
            "rel_volume": (info.get("regularMarketVolume") / info.get("averageVolume")) if info.get("regularMarketVolume") and info.get("averageVolume") else None,
            "prev_close": info.get("regularMarketPreviousClose"),
            "change_pct": info.get("regularMarketChangePercent"),
            "long_name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            # valuation
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_book": info.get("priceToBook"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "peg_ratio": info.get("trailingPegRatio") or info.get("pegRatio"),
            "dividend_yield_pct": div_y,
            "market_cap": info.get("marketCap"),
            # creștere & profitabilitate
            "eps_ttm": info.get("trailingEps"),
            "eps_forward": info.get("forwardEps"),
            "eps_5y_growth_pct": _f_eps.result(),
            "revenue_growth_yoy_pct": (info.get("revenueGrowth") * 100) if info.get("revenueGrowth") is not None else None,
            "sales_growth_3y_cagr_pct": _f_sales.result(),
            "earnings_growth_yoy_pct": (info.get("earningsGrowth") * 100) if info.get("earningsGrowth") is not None else None,
            "gross_margin_pct": (info.get("grossMargins") * 100) if info.get("grossMargins") is not None else None,
            "operating_margin_pct": (info.get("operatingMargins") * 100) if info.get("operatingMargins") is not None else None,
            "profit_margin_pct": (info.get("profitMargins") * 100) if info.get("profitMargins") is not None else None,
            "roe_pct": (info.get("returnOnEquity") * 100) if info.get("returnOnEquity") is not None else None,
            "roa_pct": (info.get("returnOnAssets") * 100) if info.get("returnOnAssets") is not None else None,
            # proprietate
            "insider_ownership_pct": (info.get("heldPercentInsiders") * 100) if info.get("heldPercentInsiders") is not None else None,
            "institutional_ownership_pct": (info.get("heldPercentInstitutions") * 100) if info.get("heldPercentInstitutions") is not None else None,
            "insider_tx_summary": insider_tx_short,
            "insider_tx_summary_full": insider_tx_full,
            # tehnic
            "sma20": sma20, "sma50": sma50, "sma200": sma200,
            "rsi14": rsi14, "atr14": atr14,
            "volatility_annual_pct": volatility_annual,
            "beta": info.get("beta"),
            "week52_high": week52_high,
            "week52_low": week52_low,
            "price_clean_notes": "; ".join(_clean_notes) or None,
            "perf_week_pct": pct_change_over(closes, 5),
            "perf_month_pct": pct_change_over(closes, 21),
            "perf_quarter_pct": pct_change_over(closes, 63),
            "perf_half_year_pct": pct_change_over(closes, 126),
            "perf_ytd_pct": pct_change_ytd(closes),
            "perf_year_pct": pct_change_over(closes, 252),
            "perf_3y_pct": pct_change_over(closes, 252 * 3),
            "perf_5y_pct": pct_change_over(closes, 252 * 5),
            "perf_10y_pct": pct_change_over(closes, 252 * 10),
            # analiști
            "target_mean_price": target_mean_price,
            "recommendation": info.get("recommendationKey"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
        }
        return result, None
    except Exception as e:
        return None, f"Eroare la interogarea Yahoo Finance: {e}"


@st.cache_data(ttl=600, show_spinner=False)
def fetch_benchmark_return(benchmark_symbol, start_date_iso):
    if not YFINANCE_AVAILABLE:
        return None, "Pachetul yfinance nu e instalat în imagine."
    try:
        hist = yf.Ticker(benchmark_symbol).history(start=start_date_iso)
        if hist.empty or len(hist) < 2:
            return None, f"Nu există date Yahoo Finance pentru „{benchmark_symbol}” în perioada respectivă."
        total_return_pct = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
        return total_return_pct, None
    except Exception as e:
        return None, f"Eroare la interogarea benchmark-ului: {e}"


@st.cache_data(ttl=300, show_spinner=False)
def fetch_price_chart_history(yahoo_symbol, period, interval):
    if not YFINANCE_AVAILABLE:
        return None, "yfinance indisponibil"
    try:
        hist = yf.Ticker(yahoo_symbol).history(period=period, interval=interval)
        if hist.empty:
            return None, f"Nu există date de preț pentru „{yahoo_symbol}” pe perioada aleasă."
        if interval in ("1d", "5d", "1wk", "1mo", "3mo"):
            hist, _ = clean_history(hist, fund=is_fund(yf.Ticker(yahoo_symbol)), spikes=(interval == "1d"))
        return hist, None
    except Exception as e:
        return None, f"Eroare la încărcarea graficului: {e}"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sector_etf_reference(sector):
    etf_symbol = SECTOR_ETF_MAP.get(sector)
    if not etf_symbol or not YFINANCE_AVAILABLE:
        return None
    try:
        info = yf.Ticker(etf_symbol).info or {}
        return {
            "etf_symbol": etf_symbol,
            "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
        }
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_yahoo_currency_hint(yahoo_symbol):
    if not YFINANCE_AVAILABLE:
        return None
    try:
        return (yf.Ticker(yahoo_symbol).info or {}).get("currency")
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo_peg_ratio(yahoo_symbol):
    if not YFINANCE_AVAILABLE:
        return None
    try:
        info = yf.Ticker(yahoo_symbol).info or {}
        return info.get("trailingPegRatio") or info.get("pegRatio")
    except Exception:
        return None
