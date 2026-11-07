"""Valoarea maxima atinsa de portofoliu si de fiecare pozitie, cu data (fara UI).

Portofoliul: din istoricul valorii (puncte la ~15 min in ultimele 30 de zile, mai vechi un punct pe zi).
Pozitiile: din reconstructia zilnica T212/XTB (inchideri Yahoo x cantitatea detinuta in ziua respectiva),
in moneda contului; valoarea de acum o inlocuieste daca e mai mare (reconstructia se opreste la ieri).
"""
import pandas as pd


def series_peak(values):
    """(valoare, 'YYYY-MM-DD') pentru maximul unei serii zilnice cu index de date; None daca nu e > 0."""
    if values is None or len(values) == 0:
        return None
    s = pd.Series(values).dropna()
    if s.empty:
        return None
    day = s.idxmax()
    v = float(s.loc[day])
    if v <= 0:
        return None
    return round(v, 2), pd.Timestamp(day).strftime("%Y-%m-%d")


def portfolio_peak(records, current=None, now=None):
    """Maximul valorii de piata din istoric: {"value", "ts", "now": bool}; current (valoarea de acum) castiga
    daca e mai mare. None fara date."""
    best = None
    for r in records or []:
        v = r.get("market_value")
        ts = r.get("ts") or r.get("date")
        if v is None or not ts:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v > 0 and (best is None or v > best["value"]):
            best = {"value": v, "ts": str(ts), "now": False}
    if current is not None and current > 0 and (best is None or current >= best["value"]):
        ts = (now or pd.Timestamp.now()).isoformat(timespec="seconds")
        best = {"value": float(current), "ts": ts, "now": True}
    return best


def peak_label(ts):
    """Textul datei maximului: 'dd.mm.yyyy' pentru o zi reconstruita (inchiderea zilei, marcata T23:00:00),
    'dd.mm.yyyy HH:MM' (ora locala) pentru un punct inregistrat."""
    ts = str(ts)
    if "T" not in ts or ts.endswith("T23:00:00"):
        return pd.Timestamp(ts[:10]).strftime("%d.%m.%Y")
    from history_multi import to_local
    return to_local(ts).strftime("%d.%m.%Y %H:%M")


def position_peaks(ticker, yahoo_symbol=None, current=None):
    """Maximele pozitiei din reconstructiile T212 si XTB: lista de {"label", "ccy", "value", "date", "now"}.
    current: {label: valoarea de acum in moneda contului}; o valoare de acum mai mare devine maximul."""
    import t212_history_rebuild
    import xtb_history_rebuild

    current = current or {}
    out = []
    for mod in (t212_history_rebuild, xtb_history_rebuild):
        try:
            peaks = mod.load_peaks()
        except Exception:
            peaks = {}
        for tk, entries in peaks.items():
            for e in entries or []:
                if tk != ticker and not (yahoo_symbol and e.get("sym") == yahoo_symbol):
                    continue
                out.append({"label": e.get("label"), "ccy": e.get("ccy"), "value": float(e["value"]),
                            "date": e["date"], "now": False})
    for p in out:
        cur = current.get(p["label"])
        if cur is not None and cur >= p["value"]:
            p.update(value=float(cur), date=pd.Timestamp.now().strftime("%Y-%m-%d"), now=True)
    return sorted(out, key=lambda p: p["label"] or "")
