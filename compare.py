"""Comparatie intre instrumente: randament normalizat si indicatori pe perioada aleasa."""
import math

import numpy as np
import pandas as pd

MAX_SYMBOLS = 5
TRADING_DAYS = 252


def normalize(closes):
    """Preturi de inchidere (coloane = simboluri) -> % fata de primul pret valid al fiecarei coloane."""
    if closes is None or closes.empty:
        return pd.DataFrame()
    out = {}
    for col in closes.columns:
        s = closes[col].dropna()
        if s.empty or not s.iloc[0]:
            continue
        out[col] = (s / s.iloc[0] - 1) * 100
    return pd.DataFrame(out)


def period_stats(series, interval="1d"):
    """Randament total, volatilitate anualizata si drawdown maxim (%) pentru o serie de preturi."""
    s = series.dropna() if series is not None else pd.Series(dtype=float)
    if len(s) < 2 or not s.iloc[0]:
        return {"return": None, "volatility": None, "max_drawdown": None}
    rets = s.pct_change().dropna()
    per_year = {"1d": TRADING_DAYS, "1wk": 52, "1mo": 12}.get(interval)
    vol = float(rets.std() * math.sqrt(per_year) * 100) if per_year and len(rets) >= 5 else None
    dd = float((s / s.cummax() - 1).min() * 100)
    return {"return": float((s.iloc[-1] / s.iloc[0] - 1) * 100), "volatility": vol, "max_drawdown": dd}


def closes_from_download(df, symbols):
    """Rezultatul yf.download (o coloana sau MultiIndex) -> DataFrame cu cate o coloana Close per simbol."""
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" not in df.columns.get_level_values(0):
            return pd.DataFrame()
        closes = df["Close"]
    else:
        closes = df[["Close"]].rename(columns={"Close": symbols[0]}) if "Close" in df.columns else pd.DataFrame()
    return closes[[s for s in symbols if s in closes.columns]]


def fundamentals(info):
    """Campurile din yfinance info folosite in tabel. Pretul si tinta vin din acelasi info (aceeasi unitate si la GBp)."""
    info = info or {}
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    target = info.get("targetMeanPrice")
    ccy = info.get("currency")
    y = info.get("dividendYield")  # Yahoo il da deja ca procent
    return {
        "name": info.get("shortName") or info.get("longName"),
        "kind": "etf" if str(info.get("quoteType") or "").upper() in ("ETF", "MUTUALFUND") else "stock",
        "currency": "GBP" if ccy == "GBp" else ccy,
        "price": price / 100 if price and ccy == "GBp" else price,
        "pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "dividend_yield": _num(y),
        "market_cap": _num(info.get("marketCap")),
        "beta": _num(info.get("beta")),
        "target_upside": (target / price - 1) * 100 if target and price else None,
        "sector": info.get("sector"),
        "country": info.get("country"),
    }


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) or np.isinf(f) else f


def parse_symbols(text):
    """Text liber "NVDA, sap.de  KO" -> ["NVDA", "SAP.DE", "KO"], fara duplicate."""
    out = []
    for part in str(text or "").replace(";", ",").replace(",", " ").split():
        p = part.strip().upper()
        if p and len(p) <= 15 and p not in out:
            out.append(p)
    return out
