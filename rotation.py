"""Rotatia sectoarelor: graficul RRG (Relative Rotation Graph) al ETF-urilor sectoriale SPDR fata de S&P 500.

RS = pretul ETF-ului / pretul SPY (saptamanal). RS-Ratio = 100 * RS / media RS pe RATIO_WEEKS (peste 100 = bate
piata pe trend); RS-Momentum = 100 + schimbarea RS-Ratio in MOM_WEEKS (peste 100 = avantajul creste). O aproximare
a metodei JdK (formula originala nu e publica). Cadrane: leading, weakening, lagging, improving.
"""
import pandas as pd

BENCH = "SPY"
# numele de sector ca la Yahoo / exposure.py -> ETF-ul SPDR
SECTOR_ETFS = {
    "Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP", "Energy": "XLE", "Industrials": "XLI", "Basic Materials": "XLB",
    "Utilities": "XLU", "Real Estate": "XLRE", "Communication Services": "XLC",
}
QUADRANTS = ("leading", "weakening", "lagging", "improving")
RATIO_WEEKS = 10
MOM_WEEKS = 4
TAIL = 5            # saptamani afisate in coada fiecarui punct
RETURN_WEEKS = (4, 13, 26, 52)


def quadrant(ratio, mom):
    if ratio >= 100:
        return "leading" if mom >= 100 else "weakening"
    return "improving" if mom >= 100 else "lagging"


def rrg(closes, tail=TAIL):
    """closes: DataFrame saptamanal cu coloanele ETF-urilor si BENCH. -> {sector: {ratio, mom, dates, quadrant}}."""
    out = {}
    if closes is None or closes.empty or BENCH not in closes.columns:
        return out
    bench = closes[BENCH]
    for sector, etf in SECTOR_ETFS.items():
        if etf not in closes.columns:
            continue
        rs = (closes[etf] / bench).dropna()
        ratio = 100 * rs / rs.rolling(RATIO_WEEKS).mean()
        mom = 100 + (ratio - ratio.shift(MOM_WEEKS))
        both = pd.DataFrame({"ratio": ratio, "mom": mom}).dropna().tail(tail)
        if both.empty:
            continue
        out[sector] = {
            "ratio": [float(x) for x in both["ratio"]], "mom": [float(x) for x in both["mom"]],
            "dates": [d.strftime("%Y-%m-%d") for d in both.index],
            "quadrant": quadrant(float(both["ratio"].iloc[-1]), float(both["mom"].iloc[-1])),
        }
    return out


def relative_returns(closes, weeks=RETURN_WEEKS):
    """Randamentul fiecarui sector minus al pietei (puncte procentuale) pe ultimele n saptamani."""
    out = {}
    if closes is None or closes.empty or BENCH not in closes.columns:
        return out
    c = closes.ffill()

    def ret(col, n):
        s = c[col].dropna()
        return (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100 if len(s) > n else None

    for sector, etf in SECTOR_ETFS.items():
        if etf in c.columns:
            out[sector] = {}
            for n in weeks:
                a, b = ret(etf, n), ret(BENCH, n)
                out[sector][n] = a - b if a is not None and b is not None else None
    return out


def portfolio_by_quadrant(sector_pct, points):
    """sector_pct: {sector: % din portofoliu}. -> {cadran: %}; restul (fara sector SPDR) la "other"."""
    out = {q: 0.0 for q in QUADRANTS}
    out["other"] = 0.0
    for sector, pct in sector_pct.items():
        q = (points.get(sector) or {}).get("quadrant")
        out[q or "other"] += pct
    return out
