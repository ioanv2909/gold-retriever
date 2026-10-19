import numpy as np

PRICE_COLS = ("Open", "High", "Low", "Close")


def is_fund(tk):
    qt = None
    try:
        qt = tk.fast_info.get("quoteType")
    except Exception:
        qt = None
    if not qt:
        try:
            qt = tk.info.get("quoteType")
        except Exception:
            qt = None
    return None if not qt else qt in ("ETF", "MUTUALFUND")


def _factors(close, fund, spikes):
    vals = close.astype(float).to_numpy().copy()
    n = len(vals)
    factors = np.ones(n)
    keep = np.ones(n, dtype=bool)
    notes = []
    idx = close.index

    if fund is not False:
        _min_k, _tol = (2, 0.03) if fund else (20, 0.01)
        for i in range(1, n):
            prev, cur = vals[i - 1], vals[i]
            if not (prev > 0 and cur > 0):
                continue
            r = cur / prev
            if 0.6 <= r <= 1.7:
                continue
            k = max(r, 1 / r)
            kr = round(k)
            if kr >= _min_k and abs(k - kr) / kr <= _tol:
                vals[:i] *= r
                factors[:i] *= r
                notes.append(f"discontinuitate ~1:{kr} la {idx[i].date()}")

    if spikes and n >= 3:
        thr = 0.08 if fund is True else 0.30
        p = 0
        for t in range(1, n - 1):
            a, b, c = vals[p], vals[t], vals[t + 1]
            if a > 0 and b > 0 and c > 0 and abs(b / a - 1) > thr and 0.97 <= c / a <= 1.03:
                keep[t] = False
                notes.append(f"preț izolat eliminat la {idx[t].date()}")
            else:
                p = t
    return factors, keep, notes


def clean_history(hist, fund=False, spikes=True):
    if hist is None or len(hist) < 3 or "Close" not in hist.columns:
        return hist, []
    factors, keep, notes = _factors(hist["Close"], fund, spikes)
    if not notes:
        return hist, []
    out = hist.copy()
    for col in PRICE_COLS:
        if col in out.columns:
            out[col] = out[col].to_numpy() * factors
    return out[keep], notes
