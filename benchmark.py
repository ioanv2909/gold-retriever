"""Linia S&P 500 de pe graficul de valoare (fara UI): cat ar valora portofoliul daca aceleasi sume ar fi fost
puse in S&P 500. La inceputul perioadei se "cumpara" indice de valoarea de piata a portofoliului; fiecare
schimbare a sumei investite cumpara sau vinde indice la pretul din acel moment."""
from datetime import datetime

import pandas as pd

SYMBOL = "^GSPC"
# perioada graficului -> (period, interval) Yahoo; intraday doar cat permite Yahoo (5m/30m 60 zile, 1h 730 zile)
YF_RANGE = {
    "3H": ("5d", "5m"), "1D": ("5d", "5m"), "1W": ("1mo", "30m"), "1M": ("3mo", "1h"),
    "3M": ("2y", "1d"), "6M": ("2y", "1d"), "YTD": ("2y", "1d"), "1Y": ("2y", "1d"),
    "3Y": ("max", "1d"), "5Y": ("max", "1d"), "Max": ("max", "1d"),
}


def to_local_naive(series):
    """Seria cu indexul in ora locala, fara fus orar (ca punctele graficului)."""
    s = series.dropna()
    idx = pd.DatetimeIndex(s.index)
    if idx.tz is not None:
        idx = idx.tz_convert(datetime.now().astimezone().tzinfo).tz_localize(None)
    s = pd.Series(s.to_numpy(dtype=float), index=idx).sort_index()
    return s[~s.index.duplicated(keep="last")]


def align(x, prices):
    """Ultimul pret cunoscut la fiecare moment din x (primele puncte, dinaintea datelor, iau primul pret)."""
    if prices is None or prices.empty:
        return pd.Series([float("nan")] * len(x))
    left = pd.DataFrame({"x": pd.to_datetime(pd.Series(list(x)))}).reset_index()
    right = pd.DataFrame({"x": prices.index, "p": prices.to_numpy()}).sort_values("x")
    m = pd.merge_asof(left.sort_values("x"), right, on="x", direction="backward").sort_values("index")
    p = m["p"].reset_index(drop=True)
    return p.bfill() if p.notna().any() else p.fillna(right["p"].iloc[0])


def simulate(market_value, invested, price):
    """Valoarea portofoliului echivalent in indice, la fiecare punct (liste/serii de aceeasi lungime)."""
    mv = [float(v) for v in market_value]
    inv = [float(v) for v in invested]
    pr = [float(v) for v in price]
    if not mv or any(p != p or p <= 0 for p in pr):
        return None
    units = mv[0] / pr[0]
    out = [mv[0]]
    for i in range(1, len(mv)):
        units = max(0.0, units + (inv[i] - inv[i - 1]) / pr[i])
        out.append(units * pr[i])
    return out
