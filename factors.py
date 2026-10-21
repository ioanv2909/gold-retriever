"""Expunerea portofoliului pe factori: regresia randamentelor saptamanale ale portofoliului actual pe piata (SPY)
si pe diferenta dintre fiecare ETF de factor si piata (stil "long factor, short market").

Portofoliul = ponderile de azi aplicate preturilor din ultimii doi ani, deci arata inclinarea pozitiilor actuale,
nu istoricul tranzactiilor. Monedele nu se convertesc (randamente in moneda fiecarui instrument).
"""
import numpy as np
import pandas as pd

MARKET = "SPY"
FACTORS = {"size": "IWM", "value": "VLUE", "momentum": "MTUM", "quality": "QUAL", "low_vol": "USMV",
           "dividend": "SCHD"}
MIN_WEEKS = 52
MIN_DATA = 0.8      # un instrument intra in portofoliu doar daca are preturi in cel putin 80% din saptamani
T_SIGNIFICANT = 2.0


def portfolio_returns(closes, weights):
    """closes: DataFrame saptamanal per simbol; weights: {simbol: valoare}. -> (randamente, acoperire %)."""
    total = sum(w for w in weights.values() if w and w > 0)
    if closes is None or closes.empty or not total:
        return pd.Series(dtype=float), 0.0
    good = [s for s, w in weights.items()
            if w and w > 0 and s in closes.columns and closes[s].notna().mean() >= MIN_DATA]
    if not good:
        return pd.Series(dtype=float), 0.0
    w = pd.Series({s: weights[s] for s in good})
    rets = closes[good].ffill().pct_change(fill_method=None).iloc[1:].fillna(0.0)
    port = (rets * (w / w.sum())).sum(axis=1)
    return port, float(w.sum() / total * 100)


def regress(port, closes):
    """OLS: port = a + b*piata + sum(c_f * (factor_f - piata)). -> {beta, tilts {f: (coef, t)}, r2, n} sau None."""
    if port is None or port.empty or closes is None or MARKET not in closes.columns:
        return None
    rets = closes.ffill().pct_change(fill_method=None)
    names = [f for f, etf in FACTORS.items() if etf in rets.columns]
    df = pd.DataFrame({"y": port, "mkt": rets[MARKET]})
    for f in names:
        df[f] = rets[FACTORS[f]] - rets[MARKET]
    df = df.dropna()
    if len(df) < MIN_WEEKS:
        return None
    X = np.column_stack([np.ones(len(df)), df["mkt"].values] + [df[f].values for f in names])
    y = df["y"].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    dof = len(y) - X.shape[1]
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(np.diag(sigma2 * np.linalg.pinv(X.T @ X)))
    tstat = coef / np.where(se > 0, se, np.nan)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "beta": float(coef[1]), "beta_t": float(tstat[1]),
        "tilts": {f: (float(coef[i + 2]), float(tstat[i + 2])) for i, f in enumerate(names)},
        "r2": 1 - float(resid @ resid) / ss_tot if ss_tot else None,
        "n": int(len(y)),
    }
