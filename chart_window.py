"""Fereastra initiala a graficelor care se pot trage in timp (fara UI): se incarca o perioada mai lunga,
iar graficul se deschide pe perioada aleasa; la tragere apar si datele dinainte."""
import pandas as pd

# perioada aleasa (CHART_PERIODS) -> perioada incarcata de la Yahoo, cu acelasi interval (~3 ferestre)
CHART_LOAD = {"1Z": "5d", "1S": "1mo", "1L": "3mo", "3L": "1y", "6L": "2y", "YTD": "2y", "1A": "2y",
              "3A": "10y", "5A": "max", "Max": "max"}
EXTRA_WINDOWS = 2  # graficul valorii: cate ferestre de dinainte se mai incarca


def view_start(index, yf_period):
    """Inceputul ferestrei alese (perioada yfinance: 1d, 5d, Nmo, Ny, ytd, max) in datele incarcate; None = tot."""
    if index is None or len(index) == 0 or yf_period == "max":
        return None
    idx = pd.DatetimeIndex(index)
    last = idx.max()
    if yf_period == "ytd":
        return pd.Timestamp(year=last.year, month=1, day=1, tz=last.tz)
    if yf_period.endswith("d"):  # zile de tranzactionare, ca la yfinance
        days = sorted(set(idx.normalize()))
        n = int(yf_period[:-1])
        first_day = days[-n] if len(days) >= n else days[0]
        return idx[idx.normalize() >= first_day].min()
    if yf_period.endswith("mo"):
        return last - pd.DateOffset(months=int(yf_period[:-2]))
    if yf_period.endswith("y"):
        return last - pd.DateOffset(years=int(yf_period[:-1]))
    return None  # perioada necunoscuta: tot graficul


def padded_range(values, pad=0.05):
    """[min, max] cu o margine, pentru axa Y fixa; None fara valori."""
    vals = [float(v) for v in values if v is not None and pd.notna(v)]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    p = max((hi - lo) * pad, abs(hi) * 0.0005)
    return [lo - p, hi + p]
